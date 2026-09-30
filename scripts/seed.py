"""Seed Firestore met de fictieve CallSight-dataset uit data/seed/, via de backend-pipeline van B.

De data loopt door dezelfde code als live calls (app.pipeline.load_solutions en load_calls), dus ID's,
embeddings, suggesties en tellers zijn identiek aan wat de webhook zou doen. Datums staan als `days_ago`
in de JSON en worden hier omgerekend ten opzichte van nu, zodat recency op de demodag klopt.

Een tweede pas vult aan wat de pipeline niet kent: trust-signalen op solutions (country, source,
owner_expert, last_reviewed_at, conflicts_with), sector/size/country en de KBO-controle (kbo) op companies,
en role op callers. De KBO-treffers komen uit data/seed/kbo.json (gemaakt met scripts/kbo_lookup.py).

Gebruik (backend-venv actief, vanuit de repo-root):
  python scripts/seed.py --check          # alleen valideren, geen GCP
  python scripts/seed.py --offline        # volledige run in geheugen, geen GCP (hash-embedder, of het
                                          # lokale model als EMBEDDING_PROVIDER=local: dan kloppen de scores)
  python scripts/seed.py --reset --yes    # Firestore wissen en opnieuw vullen
  python scripts/seed.py --probe          # alleen de demo-scenario's scoren tegen de huidige kennisbank

Gebruik altijd dezelfde EMBEDDING_PROVIDER, EMBEDDING_MODEL en EMBEDDING_DIM als de backend op Cloud Run
(nu: local, sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2, 384; zie docs/backend.md),
anders zijn de similarities betekenisloos.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

SEED_DIR = REPO_ROOT / "data" / "seed"
COLLECTIONS = ("calls", "callers", "companies", "solutions")
AGENT_GREETING = "Goeiedag, u spreekt met de digitale assistent van SD Worx. Ik ben een AI. Met wie spreek ik?"
# Het probleem zoals de agent het bij de drie demo-scenario's zou vastleggen (docs/demo-script.md).
PROBES = {
    "a (terugkerende beller)": "Een consultant die vorige maand uit dienst ging, krijgt veel minder vertrekvakantiegeld "
    "dan verwacht; het vakantiegeld van vorig jaar lijkt er niet in te zitten.",
    "b (nieuwe beller)": "Hoeveel maaltijdcheques krijgt een verkoopster die drie dagen per week werkt?",
    "c (onbekend probleem)": "Een arbeider gaat drie maanden telewerken vanuit Spanje; wat moet er geregeld worden "
    "voor de sociale zekerheid?",
}
DEMO_IDS = {"caller": "lindsey-tafels--united-consulting", "company": "united-consulting"}

log = logging.getLogger("seed")


def load(name: str) -> list[dict[str, Any]]:
    return json.loads((SEED_DIR / f"{name}.json").read_text(encoding="utf-8"))


def validate(companies, callers, solutions, calls, experts) -> list[str]:
    from app.models import CATEGORIES, URGENCIES
    from app.pipeline import company_id_for

    errors: list[str] = []
    company_names = {c["name"] for c in companies}
    if len({company_id_for(n) for n in company_names}) != len(company_names):
        errors.append("twee bedrijven krijgen hetzelfde company_id")
    caller_keys = {(c["name"], c["company"]) for c in callers}
    by_id = {s["id"]: s for s in solutions}
    expert_ids = {e["id"] for e in experts}
    for c in callers:
        if c["company"] not in company_names:
            errors.append(f"beller {c['name']}: onbekend bedrijf {c['company']}")
    for s in solutions:
        if s["category"] not in CATEGORIES:
            errors.append(f"{s['id']}: onbekende category {s['category']}")
        if s["owner"] and s["owner"] not in expert_ids:
            errors.append(f"{s['id']}: onbekende owner {s['owner']}")
        if s["prior_successful"] > s["prior_used"]:
            errors.append(f"{s['id']}: prior_successful > prior_used")
        errors += [f"{s['id']}: conflicts_with onbekend {o}" for o in s["conflicts_with"] if o not in by_id]
    for i, call in enumerate(calls):
        where = f"call #{i} ({call['caller']})"
        if (call["caller"], call["company"]) not in caller_keys:
            errors.append(f"{where}: beller niet in callers.json")
        if call["category"] not in CATEGORIES or call["urgency"] not in URGENCIES:
            errors.append(f"{where}: ongeldige category of urgency")
        if call["days_ago"] < 1:
            errors.append(f"{where}: days_ago moet minstens 1 zijn")
        if call["solution"] is not None:
            if call["solution"] not in by_id:
                errors.append(f"{where}: onbekende solution {call['solution']}")
            elif by_id[call["solution"]]["category"] != call["category"]:
                errors.append(f"{where}: category wijkt af van {call['solution']}")
        if (call["solution"] is None) != (call["worked"] is None):
            errors.append(f"{where}: solution en worked zijn allebei null (open) of allebei gevuld")
    with_calls = {(c["caller"], c["company"]) for c in calls}
    errors += [f"beller {n} ({co}) heeft geen calls" for n, co in caller_keys - with_calls]
    return errors


def ago(now: datetime, days: Optional[int]) -> Optional[datetime]:
    return None if days is None else now - timedelta(days=days)


def solution_rows(solutions, now: datetime) -> list[dict[str, Any]]:
    """Formaat van app.models.SolutionIn. times_used telt alleen de historie van vóór de seed-calls:
    elke seed-call met een resolution verhoogt de tellers via de pipeline."""
    return [
        {
            "solution_id": s["id"], "title": s["title"], "problem_text": s["problem_text"],
            "solution_text": s["solution_text"], "category": s["category"],
            "times_used": s["prior_used"], "times_successful": s["prior_successful"],
            "last_used_at": ago(now, s["last_used_days_ago"]),
        }
        for s in solutions
    ]


def call_payloads(calls, now: datetime) -> list[dict[str, Any]]:
    """ElevenLabs post-call payloads (zoals backend/samples/call_*.json), oudste eerst, met resolution."""
    rows = []
    ordered = sorted(calls, key=lambda c: (-c["days_ago"], c["caller"]))
    for n, c in enumerate(ordered):
        day = now - timedelta(days=c["days_ago"])
        started = day.replace(hour=8 + n % 9, minute=(n * 7) % 60, second=0, microsecond=0)
        collected = {"caller_name": c["caller"], "company_name": c["company"], "problem": c["problem"],
                     "category": c["category"], "urgency": c["urgency"]}
        row: dict[str, Any] = {
            "type": "post_call_transcription",
            "data": {
                "conversation_id": f"seed-{n:03d}",
                "agent_id": "seed",
                "status": "done",
                "transcript": [
                    {"role": "agent", "message": AGENT_GREETING, "time_in_call_secs": 0},
                    {"role": "user", "message": f"Goeiedag, met {c['caller']} van {c['company']}. {c['problem']}",
                     "time_in_call_secs": 4},
                ],
                "metadata": {"start_time_unix_secs": int(started.timestamp()), "call_duration_secs": c["duration"]},
                "analysis": {
                    "transcript_summary": c["problem"],
                    "data_collection_results": {k: {"value": v} for k, v in collected.items()},
                },
            },
        }
        if c["solution"]:
            resolved = min(started + timedelta(days=1), now - timedelta(hours=1))
            row["resolution"] = {"solution_id": c["solution"], "worked": bool(c["worked"]),
                                 "resolved_at": resolved.isoformat()}
        rows.append(row)
    return rows


def merge(store, collection: str, doc_id: str, fields: dict[str, Any]) -> None:
    """Extra velden bijschrijven zonder de documenten van de pipeline te overschrijven."""
    db = getattr(store, "db", None)
    if db is not None:
        db.collection(collection).document(doc_id).set(fields, merge=True)
    else:  # MemoryStore
        getattr(store, collection).setdefault(doc_id, {}).update(fields)


def kbo_field(kbo: Optional[dict[str, Any]], company_id: str) -> Optional[dict[str, Any]]:
    """KBO-controle voor het dashboard: uniek, meerdere (bevestigen) of niet_gevonden."""
    if not kbo or company_id not in kbo.get("companies", {}):
        return None
    matches = kbo["companies"][company_id]
    status = "niet_gevonden" if not matches else "uniek" if len(matches) == 1 else "meerdere"
    return {"status": status, "matches": matches, "source": kbo.get("source"), "snapshot": kbo.get("snapshot")}


def enrich(store, companies, callers, solutions, experts, payloads, now: datetime,
           kbo: Optional[dict[str, Any]] = None) -> None:
    from app.pipeline import caller_id_for, company_id_for

    experts_by_id = {e["id"]: e for e in experts}
    last_resolution: dict[str, datetime] = {}
    for row in payloads:
        res = row.get("resolution")
        if res:
            when = datetime.fromisoformat(res["resolved_at"])
            last_resolution[res["solution_id"]] = max(when, last_resolution.get(res["solution_id"], when))
    for s in solutions:
        owner = experts_by_id.get(s["owner"]) if s["owner"] else None
        candidates = [d for d in (ago(now, s["last_used_days_ago"]), last_resolution.get(s["id"])) if d]
        merge(store, "solutions", s["id"], {
            "country": s["country"],
            "source": s["source"],
            "owner_expert": {k: owner[k] for k in ("id", "name", "team")} if owner else None,
            "last_reviewed_at": ago(now, s["last_reviewed_days_ago"]),
            "conflicts_with": s["conflicts_with"],
            "last_used_at": max(candidates) if candidates else None,
        })
    for c in companies:
        cid = company_id_for(c["name"])
        merge(store, "companies", cid, {"sector": c["sector"], "size": str(c["size"]), "country": c["country"],
                                         "kbo": kbo_field(kbo, cid)})
    for c in callers:
        if c.get("role"):
            merge(store, "callers", caller_id_for(c["name"], company_id_for(c["company"])), {"role": c["role"]})


def wipe(store) -> None:
    db = getattr(store, "db", None)
    if db is None:
        return
    for name in COLLECTIONS:
        batch, n = db.batch(), 0
        for ref in db.collection(name).list_documents(page_size=300):
            batch.delete(ref)
            n += 1
            if n % 400 == 0:
                batch.commit()
                batch = db.batch()
        batch.commit()
        log.info("%s: %d documenten gewist", name, n)


def probe(store, embedder, threshold: int, now: datetime) -> None:
    """Scoor de drie demo-problemen tegen de kennisbank: voor de kalibratie in docs/demo-script.md."""
    from app.embeddings import TASK_QUERY
    from app.pipeline import needs_escalation, suggest

    log.info("demo-scenario's (drempel escaleren: %d):", threshold)
    for label, text in PROBES.items():
        try:
            suggestions = suggest(store, embedder.embed([text], TASK_QUERY)[0], now)
        except Exception as exc:  # noqa: BLE001 - meestal een vector-index die nog bouwt
            log.warning("  %s: zoeken mislukt (%s); staat de vector-index al klaar?", label, type(exc).__name__)
            continue
        top = " | ".join(f"{s['solution_id']} {s['score']} (sim {s['reasons']['similarity']:.2f})" for s in suggestions[:3])
        log.info("  %-24s %s  -> escaleren: %s", label, top, needs_escalation(suggestions, threshold))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="alleen valideren en samenvatten")
    parser.add_argument("--offline", action="store_true", help="in geheugen met de hash-embedder (geen GCP)")
    parser.add_argument("--reset", action="store_true", help="calls, callers, companies en solutions eerst wissen")
    parser.add_argument("--yes", action="store_true", help="bevestig --reset")
    parser.add_argument("--probe", action="store_true", help="alleen de demo-scenario's scoren, niets schrijven")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    data = {name: load(name) for name in ("companies", "callers", "solutions", "calls", "experts")}
    errors = validate(**data)
    if errors:
        for e in errors:
            log.error(e)
        return 1
    open_calls = sum(c["solution"] is None for c in data["calls"])
    log.info("ok: %d bedrijven, %d bellers, %d solutions, %d calls (%d open), %d experten",
             len(data["companies"]), len(data["callers"]), len(data["solutions"]), len(data["calls"]),
             open_calls, len(data["experts"]))
    if args.check:
        return 0
    if args.reset and not args.yes and not args.offline:
        log.error("--reset wist ALLE calls in Firestore, ook testcalls van het team. Bevestig met --yes.")
        return 2

    from app.config import get_settings
    from app.embeddings import make_embedder
    from app.pipeline import load_calls, load_solutions
    from app.store import make_store

    settings = get_settings()
    if args.offline:
        settings = settings.model_copy(update={"store_backend": "memory"})
    store, embedder = make_store(settings), make_embedder(settings)
    if args.offline and settings.embedding_provider == "local":
        # zelfde model als de backend op Cloud Run, maar zonder GCP: bruikbaar om de drempel te kalibreren
        from app.embeddings import LocalEmbedder

        embedder = LocalEmbedder(settings.embedding_model, settings.embedding_dim)
    now = datetime.now(timezone.utc)

    if args.probe and not args.offline:
        probe(store, embedder, settings.escalation_threshold, now)
        return 0
    if args.reset:
        wipe(store)

    payloads = call_payloads(data["calls"], now)
    n = load_solutions(store, embedder, solution_rows(data["solutions"], now))
    log.info("solutions: %d geladen", n)
    stats = load_calls(store, embedder, payloads, settings.escalation_threshold)
    log.info("calls: %(created)d aangemaakt, %(skipped)d bestonden al, %(resolved)d opgelost", stats)
    kbo_file = SEED_DIR / "kbo.json"
    kbo = json.loads(kbo_file.read_text(encoding="utf-8")) if kbo_file.exists() else None
    enrich(store, data["companies"], data["callers"], data["solutions"], data["experts"], payloads, now, kbo)
    log.info("trust-signalen, bedrijfsgegevens en rollen bijgeschreven")

    caller, company = store.get_caller(DEMO_IDS["caller"]), store.get_company(DEMO_IDS["company"])
    if caller and company:
        log.info("demo-beller %s: %d calls; bedrijf %s: %d calls, %d open",
                 DEMO_IDS["caller"], caller["call_count"], DEMO_IDS["company"], company["call_count"],
                 company["open_issues"])
    else:
        log.warning("demo-beller of -bedrijf niet gevonden na het laden")
    probe(store, embedder, settings.escalation_threshold, now)
    return 0


if __name__ == "__main__":
    sys.exit(main())
