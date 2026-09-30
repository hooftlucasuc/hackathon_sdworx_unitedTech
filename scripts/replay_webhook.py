#!/usr/bin/env python3
"""Stuurt een opgeslagen post-call payload met geldige ElevenLabs-Signature naar de backend.

Hiermee kunnen B en C testen zonder een echt gesprek te voeren, en kan D de
integratietest draaien.

    python scripts/replay_webhook.py                                  # alle samples/postcall_*.json
    python scripts/replay_webhook.py samples/postcall_01.json
    python scripts/replay_webhook.py backend/samples/call_vakantiegeld.json --new-id
    python scripts/replay_webhook.py --url https://<cloud-run>/webhooks/elevenlabs
    python scripts/replay_webhook.py --skew -3600                     # moet 401 geven

De handtekening: header `ElevenLabs-Signature: t=<unix>,v0=<hex>`, waarbij v0 de
HMAC-SHA256 is van "<t>.<rauwe body>" met het webhook-secret. Dat is geverifieerd
tegen de broncode van de ElevenLabs-SDK, zie docs/elevenlabs-payload-check.md.

Deze zeven regels staan bewust ook in backend/app/signature.py. Dat is geen toeval dat
mis kan gaan: lopen ze uiteen, dan geeft dit script meteen een 401 en weet je het.

Alleen stdlib, zodat dit draait op elke laptop in het team zonder venv of pip install.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("replay_webhook")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "http://localhost:8000/webhooks/elevenlabs"
TIMEOUT_SECS = 30


def load_env(path: Path) -> None:
    """Zet KEY=VALUE uit een .env in os.environ, zonder een bestaande waarde te overschrijven."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def sign(body: bytes, secret: str, timestamp: Optional[int] = None) -> str:
    """Bouwt de header-waarde voor deze exacte bytes."""
    ts = int(timestamp if timestamp is not None else time.time())
    digest = hmac.new(secret.encode("utf-8"), f"{ts}.".encode("utf-8") + body, hashlib.sha256).hexdigest()
    return f"t={ts},v0={digest}"


def freshen(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Geeft de payload een nieuw conversation_id en een tijdstip van nu.

    Zonder dit is een replay dezelfde call: de backend upsert op conversation_id en het
    dashboard springt niet. Met dit vlaggetje wordt elke replay een nieuwe call, wat je
    wil bij het demonstreren van het live-scherm.
    """
    now = int(time.time())
    data = payload.setdefault("data", {})
    data["conversation_id"] = f"conv_replay_{uuid.uuid4().hex[:12]}"
    payload["event_timestamp"] = now
    metadata = data.setdefault("metadata", {})
    duration = metadata.get("call_duration_secs", 0)
    metadata["start_time_unix_secs"] = now - int(duration or 0)
    return payload


def post(url: str, body: bytes, header: Optional[str]) -> int:
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    if header is not None:
        request.add_header("ElevenLabs-Signature", header)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECS) as response:
            log.info("HTTP %s  %s", response.status, response.read().decode("utf-8", "replace")[:500])
            return response.status
    except urllib.error.HTTPError as exc:
        log.error("HTTP %s  %s", exc.code, exc.read().decode("utf-8", "replace")[:500])
        return exc.code
    except urllib.error.URLError as exc:
        log.error("onbereikbaar: %s", exc.reason)
        return 0


def resolve_payloads(paths: List[str]) -> List[Path]:
    if paths:
        return [Path(p) for p in paths]
    found = sorted((REPO_ROOT / "samples").glob("postcall_*.json"))
    if not found:
        found = sorted((REPO_ROOT / "backend" / "samples").glob("call_*.json"))
        if found:
            log.info("geen samples/postcall_*.json; val terug op de demo-payloads van B")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("payloads", nargs="*", help="JSON-bestanden (default: samples/postcall_*.json)")
    parser.add_argument("--url", default=None, help=f"doel-URL (default: {DEFAULT_URL}, of env WEBHOOK_URL)")
    parser.add_argument("--secret", default=None, help="overschrijft ELEVENLABS_WEBHOOK_SECRET")
    parser.add_argument("--new-id", action="store_true", help="nieuw conversation_id en tijdstip: landt als nieuwe call")
    parser.add_argument("--skew", type=int, default=0, help="seconden bij de timestamp optellen (om afwijzing te testen)")
    parser.add_argument("--no-sign", action="store_true", help="geen header meesturen (voor /demo/simulate-call)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    load_env(REPO_ROOT / ".env")

    url = args.url or os.environ.get("WEBHOOK_URL") or DEFAULT_URL
    secret = args.secret or os.environ.get("ELEVENLABS_WEBHOOK_SECRET", "").strip()
    if not secret and not args.no_sign:
        log.error("ELEVENLABS_WEBHOOK_SECRET ontbreekt (zet hem in .env, of gebruik --no-sign)")
        return 2

    payloads = resolve_payloads(args.payloads)
    if not payloads:
        log.error("geen payloads gevonden; geef een bestand op of zet er een in samples/")
        return 2

    failures = 0
    for path in payloads:
        if not path.is_file():
            log.error("%s bestaat niet", path)
            failures += 1
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if args.new_id:
            payload = freshen(payload)
        # Onderteken exact de bytes die we versturen: opnieuw serialiseren na het
        # ondertekenen breekt de hash op een spatie.
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = None if args.no_sign else sign(body, secret, int(time.time()) + args.skew)

        conversation_id = payload.get("data", {}).get("conversation_id", "?")
        log.info("%s -> %s  (conversation_id=%s)", path.name, url, conversation_id)
        status = post(url, body, header)
        if status != 200:
            failures += 1

    if failures:
        log.error("%s van de %s mislukt", failures, len(payloads))
        return 1
    log.info("%s payload(s) verstuurd, alles 200", len(payloads))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
