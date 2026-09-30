#!/usr/bin/env python3
"""End-to-end controle van CallSight: gesprek erin, Trust Card eruit, historie en oplossen.

Twee manieren om te draaien:

  # 1. In-process, zonder server en zonder GCP (memory store + hash-embedder). Instant.
  python scripts/smoke_test.py

  # 2. Tegen een echte backend (lokaal of Cloud Run), die naar Firestore schrijft.
  python scripts/smoke_test.py --url http://localhost:8080
  python scripts/smoke_test.py --url https://callsight-backend-xxxx.europe-west1.run.app

Het script post drie voorbeeldgesprekken via /demo/simulate-call (dezelfde weg als de
ElevenLabs-webhook, maar zonder handtekening), leest ze terug en controleert dat:
  - de call in de opslag staat met beller, bedrijf, categorie en urgentie;
  - er maximaal vijf gescoorde oplossingen zijn, hoogste eerst, elk 0-100;
  - de bellerhistorie en bedrijfshistorie meegroeien;
  - /calls/{id}/resolve de tellers van de gekozen oplossing verhoogt.

Alleen stdlib, zodat dit op elke laptop draait. In-process modus importeert de backend.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

SAMPLES = Path(__file__).resolve().parent.parent / "backend" / "samples"
SCENARIOS = [
    ("call_vakantiegeld.json", "Terugkerende beller, vraag over vakantiegeld"),
    ("call_zelfde_bedrijf.json", "Andere beller, zelfde bedrijf"),
    ("call_nieuw_probleem.json", "Onbekend probleem, hoort te escaleren"),
]

GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
_checks = {"pass": 0, "fail": 0}


def _parse(raw: bytes) -> Any:
    """Return parsed JSON, or a short snippet of the raw body when it is not JSON (e.g. a 403 HTML page)."""
    text = (raw or b"").decode("utf-8", "replace").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        snippet = " ".join(text.split())[:200]
        return {"non_json_body": snippet}


def check(ok: bool, label: str) -> None:
    mark = f"{GREEN}OK{RESET}" if ok else f"{RED}FOUT{RESET}"
    print(f"  [{mark}] {label}")
    _checks["pass" if ok else "fail"] += 1


# --------------------------------------------------------------------------------------------------
# Transport: HTTP naar een echte backend, of in-process via de app met een memory store.
# --------------------------------------------------------------------------------------------------


class HttpClient:
    def __init__(self, base: str):
        # In Cloud Shell `localhost` resolves to IPv6 ::1 while uvicorn listens on IPv4; force 127.0.0.1.
        base = base.replace("://localhost", "://127.0.0.1")
        self.base = base.rstrip("/")

    def _req(self, method: str, path: str, body: Optional[dict] = None) -> tuple[int, Any]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return resp.status, _parse(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _parse(exc.read())
        except (urllib.error.URLError, OSError) as exc:
            raise SystemExit(
                f"\n{RED}Kan de backend niet bereiken op {self.base}{RESET}\n"
                f"  Reden: {exc}\n"
                f"  Draait de server nog? Start hem in een apart tabblad (of met & op de achtergrond):\n"
                f"    uvicorn app.main:app --host 127.0.0.1 --port 8080\n"
            ) from exc

    def get(self, path: str) -> tuple[int, Any]:
        return self._req("GET", path)

    def post(self, path: str, body: dict) -> tuple[int, Any]:
        return self._req("POST", path, body)


class InProcessClient:
    """Runs the FastAPI app in memory, no server, no GCP. Uses the hash embedder."""

    def __init__(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
        from fastapi.testclient import TestClient

        from app.config import Settings
        from app.main import create_app

        settings = Settings(
            _env_file=None,
            store_backend="memory",
            demo_mode=True,
            elevenlabs_webhook_secret="dev",
            embedding_provider="hash",
            memory_seed_file=SAMPLES / "solutions.json",
        )
        self._c = TestClient(create_app(settings))

    def get(self, path: str) -> tuple[int, Any]:
        r = self._c.get(path)
        return r.status_code, (r.json() if r.content else None)

    def post(self, path: str, body: dict) -> tuple[int, Any]:
        r = self._c.post(path, json=body)
        return r.status_code, (r.json() if r.content else None)


# --------------------------------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------------------------------


def print_card(call: dict) -> None:
    print(f"    {BOLD}{call.get('caller_name')}{RESET}  ·  {call.get('company_name')}")
    print(f"    {DIM}categorie{RESET} {call.get('category')}   "
          f"{DIM}urgentie{RESET} {call.get('urgency')}   "
          f"{DIM}score{RESET} {call.get('best_score')}   "
          f"{DIM}escaleren{RESET} {call.get('escalate')}")
    for i, s in enumerate(call.get("suggestions", []), 1):
        r = s["reasons"]
        print(f"      {i}. {s['score']:>3}  {s['solution_id']:<38} "
              f"{DIM}sim {r['similarity']:.2f} · succes {r['success']:.2f} · recent {r['recency']:.2f}{RESET}")


def run(client) -> None:
    print(f"\n{BOLD}1. Backend bereikbaar{RESET}")
    # /health is new; older deployed images only answer on the OpenAPI document, which is fine as a liveness probe
    status, health = client.get("/health")
    path = "/health"
    if status == 404:
        status, _ = client.get("/openapi.json")
        path, health = "/openapi.json", "app draait (oude image zonder /health)"
    check(status == 200, f"GET {path} -> {status} {health if status == 200 else ''}")
    if status != 200:
        return

    last_id = None
    for filename, title in SCENARIOS:
        payload = json.loads((SAMPLES / filename).read_text(encoding="utf-8"))
        print(f"\n{BOLD}2. Gesprek posten: {title}{RESET}")
        status, ack = client.post("/demo/simulate-call", payload)
        ok = status == 200 and ack.get("created")
        check(ok, f"POST /demo/simulate-call -> {status} (call_id {ack.get('call_id') if ok else ack})")
        if not ok:
            continue
        last_id = ack["call_id"]

        status, call = client.get(f"/calls/{last_id}")
        check(status == 200, f"GET /calls/{last_id}")
        check(bool(call.get("caller_id")), "beller herkend en gekoppeld")
        check(bool(call.get("company_id")), "bedrijf herkend en gekoppeld")
        sugg = call.get("suggestions", [])
        scores = [s["score"] for s in sugg]
        check(len(sugg) <= 5, f"maximaal 5 oplossingen ({len(sugg)})")
        check(scores == sorted(scores, reverse=True), "oplossingen gesorteerd op score, hoogste eerst")
        check(all(0 <= s <= 100 for s in scores), "alle scores tussen 0 en 100")
        check("problem_embedding" not in call, "embedding niet meegestuurd naar de UI")
        print_card(call)

    if last_id is None:
        return

    print(f"\n{BOLD}3. Historie{RESET}")
    _, call = client.get(f"/calls/{last_id}")
    caller_id, company_id = call.get("caller_id"), call.get("company_id")
    status, caller = client.get(f"/callers/{caller_id}")
    check(status == 200 and caller["caller"]["call_count"] >= 1, f"bellerhistorie {caller_id}")
    status, company = client.get(f"/companies/{company_id}")
    n = len(company.get("calls", [])) if status == 200 else 0
    check(status == 200 and n >= 1, f"bedrijfshistorie {company_id}: {n} call(s)")
    check(all("transcript" not in c for c in company.get("calls", [])), "historie bevat geen transcript")

    print(f"\n{BOLD}4. Oplossen (self-healing: tellers omhoog){RESET}")
    status, details = client.get(f"/calls/{last_id}/suggestions")
    if status == 200 and details:
        top = details[0]
        before = top.get("times_used", 0)
        status, res = client.post(f"/calls/{last_id}/resolve", {"solution_id": top["solution_id"], "worked": True})
        check(status == 200 and res.get("status") == "resolved", f"call opgelost met {top['solution_id']}")
        status, after = client.get(f"/calls/{last_id}/suggestions")
        used_after = next((s["times_used"] for s in after if s["solution_id"] == top["solution_id"]), before)
        check(used_after == before + 1, f"times_used {before} -> {used_after}")
        status, again = client.post(f"/calls/{last_id}/resolve", {"solution_id": top["solution_id"], "worked": True})
        check(status == 409, "tweede keer oplossen wordt geweigerd (409)")
    else:
        check(False, "geen oplossingen om mee te resolven")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="backend-URL; zonder deze vlag draait het in-process (memory store)")
    args = ap.parse_args()

    if args.url:
        print(f"{DIM}Modus: HTTP tegen {args.url} (echte opslag){RESET}")
        client: Any = HttpClient(args.url)
    else:
        print(f"{DIM}Modus: in-process, memory store, hash-embedder (geen GCP nodig){RESET}")
        client = InProcessClient()

    run(client)

    total = _checks["pass"] + _checks["fail"]
    print(f"\n{BOLD}Resultaat: {_checks['pass']}/{total} checks geslaagd{RESET}")
    if _checks["fail"]:
        print(f"{RED}Er zijn checks mislukt.{RESET}")
        return 1
    print(f"{GREEN}Alles werkt: gesprek -> opslag -> Trust Card -> historie -> oplossen.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
