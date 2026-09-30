#!/usr/bin/env python3
"""Luistert mee met een gesprek en stuurt de transcript stuk voor stuk door.

Dit is de luisterkant van CallSight: ElevenLabs praat niet mee, het transcribeert
alleen. Scribe v2 Realtime levert via een WebSocket doorlopend `partial_transcript`
(mag nog veranderen) en per segment `committed_transcript` (staat vast).

    python scripts/scribe_listen.py --audio samples/audio/vakantiegeld.pcm
    python scripts/scribe_listen.py --audio ... --speaker beller --push-url http://localhost:8600/segment

Eén sessie is één spreker. Scribe Realtime kent geen diarisatie — de batch-API wel,
maar die werkt pas ná het gesprek. Daarom scheiden we bij de bron: beller en
medewerker krijgen elk hun eigen microfoon en dus hun eigen sessie. Dat is
betrouwbaarder dan een model dat stemmen uit elkaar moet houden op een telefoonlijn.

Audio moet raw PCM zijn: 16-bit signed little-endian, mono. De sample rate geef je
mee met --sample-rate (standaard 16000).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional

import websockets

log = logging.getLogger("scribe_listen")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WS = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
SAMPLE_WIDTH = 2  # 16-bit
MAX_KEYTERM_CHARS = 20  # limiet van Scribe v2 Realtime; batch mag 50
# Scribe herkent deze zelf, zonder taalmodel. Dat levert de beller en het bedrijf
# betrouwbaarder op dan een regex, en het werkt ook als iemand zich niet netjes voorstelt.
ENTITY_TYPES = ["name", "name_family", "organization"]

# Zelfde lijst als de ASR-keywords van de agentconfig: zonder boost komen Dimona,
# DmfA en C4 er verminkt uit, en dan mist de extractie de categorie.
KEYTERMS = [
    "SD Worx",
    "vakantiegeld",
    "vertrekvakantiegeld",
    "Dimona",
    "DmfA",
    "maaltijdcheques",
    "ecocheques",
    "RSZ",
    "bedrijfsvoorheffing",
    "paritair comite",
    "C4",
    "opzegtermijn",
    "voordeel alle aard",
    "gewaarborgd loon",
    "loonrun",
]


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


def build_url(base: str, language: str, sample_rate: int, use_keyterms: bool) -> str:
    params: List[tuple] = [
        ("model_id", "scribe_v2_realtime"),
        ("language_code", language),
        ("commit_strategy", "vad"),
        ("include_timestamps", "false"),
    ]
    if use_keyterms:
        # Eén `keyterms` per term, herhaald. Een JSON-array of een komma-gescheiden
        # string is één term van meer dan 20 tekens, en dan sluit de server de
        # WebSocket met een kaal 1008 invalid_request zonder verdere uitleg.
        params += [("keyterms", term) for term in KEYTERMS if len(term) <= MAX_KEYTERM_CHARS]
    params += [("entity_detection", kind) for kind in ENTITY_TYPES]
    return f"{base}?{urllib.parse.urlencode(params)}"


def push_segment(url: str, call_id: str, speaker: str, text: str, entities: Optional[list] = None) -> None:
    """Stuurt één vastgezet segment naar de verzamelaar. Faalt nooit hard: de luisteraar
    moet blijven luisteren, ook als de backend even weg is."""
    payload = {"call_id": call_id, "speaker": speaker, "text": text}
    if entities:
        payload["entities"] = entities
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            log.debug("segment gepusht: HTTP %s", response.status)
    except Exception as exc:  # noqa: BLE001 - doelbewust: dit mag het luisteren niet breken
        log.warning("segment niet gepusht: %s", exc)


async def listen(
    audio: bytes,
    api_key: str,
    *,
    language: str,
    sample_rate: int,
    chunk_ms: int,
    speed: float,
    speaker: str,
    call_id: str,
    push_url: Optional[str],
    use_keyterms: bool,
) -> List[str]:
    url = build_url(DEFAULT_WS, language, sample_rate, use_keyterms)
    chunk_bytes = int(sample_rate * SAMPLE_WIDTH * chunk_ms / 1000)
    committed: List[str] = []
    started = time.monotonic()

    async with websockets.connect(url, additional_headers={"xi-api-key": api_key}) as ws:

        async def receive() -> None:
            async for raw in ws:
                event = json.loads(raw)
                kind = event.get("message_type")
                if kind == "session_started":
                    log.info("sessie gestart (%s)", speaker)
                elif kind == "partial_transcript":
                    text = (event.get("text") or "").strip()
                    if text:
                        print(f"\r  … {text[-90:]}", end="", flush=True)
                elif kind == "committed_transcript":
                    text = (event.get("text") or "").strip()
                    if not text:
                        continue
                    committed.append(text)
                    elapsed = time.monotonic() - started
                    print(f"\r[{elapsed:5.1f}s] {speaker}: {text}")
                    if push_url:
                        await asyncio.to_thread(push_segment, push_url, call_id, speaker, text)
                elif kind == "committed_transcript_entities":
                    # Eigen event, net na committed_transcript. We sturen het los na;
                    # de verzamelaar herkent dezelfde tekst en vult de entiteiten aan
                    # in plaats van er een beurt bij te zetten.
                    entities = event.get("entities") or []
                    text = (event.get("text") or "").strip()
                    if entities and text:
                        soorten = ", ".join(sorted({e.get("entity_type", "?") for e in entities}))
                        log.info("entiteiten: %s", soorten)
                        if push_url:
                            await asyncio.to_thread(push_segment, push_url, call_id, speaker, text, entities)
                elif kind in {"error", "auth_error", "quota_exceeded"}:
                    log.error("%s: %s", kind, event)
                    return
                elif kind == "commit_throttled":
                    log.warning("commit throttled")
                elif kind == "warning":
                    log.warning("%s", event.get("message") or event)

        receiver = asyncio.create_task(receive())

        pace = (chunk_ms / 1000.0) / max(speed, 0.01)
        for offset in range(0, len(audio), chunk_bytes):
            chunk = audio[offset : offset + chunk_bytes]
            last = offset + chunk_bytes >= len(audio)
            await ws.send(
                json.dumps(
                    {
                        "message_type": "input_audio_chunk",
                        "audio_base_64": base64.b64encode(chunk).decode("ascii"),
                        "commit": last,  # laatste stuk: forceer een commit, anders blijft de staart hangen
                        "sample_rate": sample_rate,
                    }
                )
            )
            await asyncio.sleep(pace)

        # Even wachten op de laatste committed_transcript voor we de sessie sluiten.
        try:
            await asyncio.wait_for(asyncio.shield(receiver), timeout=10)
        except asyncio.TimeoutError:
            pass
        receiver.cancel()

    return committed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--audio", required=True, help="raw PCM-bestand (16-bit LE, mono)")
    parser.add_argument("--language", default="nld", help="taalcode (default nld)")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--chunk-ms", type=int, default=200, help="grootte van een audiochunk in ms")
    parser.add_argument("--speed", type=float, default=1.0, help="1.0 = echte tijd, 4.0 = vier keer sneller testen")
    parser.add_argument("--speaker", default="beller", choices=["beller", "medewerker"])
    parser.add_argument("--call-id", default=None, help="id van het gesprek (default: afgeleid van de tijd)")
    parser.add_argument("--push-url", default=None, help="POST elk vastgezet segment hierheen")
    parser.add_argument("--no-keyterms", action="store_true", help="zonder de payroll-woordenlijst")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    load_env(REPO_ROOT / ".env")

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        log.error("ELEVENLABS_API_KEY ontbreekt")
        return 2

    path = Path(args.audio)
    if not path.is_file():
        log.error("%s bestaat niet", path)
        return 2
    audio = path.read_bytes()
    seconds = len(audio) / (args.sample_rate * SAMPLE_WIDTH)
    call_id = args.call_id or f"call_{int(time.time())}"
    log.info("%s: %.1f s audio, %s, call_id=%s", path.name, seconds, args.speaker, call_id)

    committed = asyncio.run(
        listen(
            audio,
            api_key,
            language=args.language,
            sample_rate=args.sample_rate,
            chunk_ms=args.chunk_ms,
            speed=args.speed,
            speaker=args.speaker,
            call_id=call_id,
            push_url=args.push_url,
            use_keyterms=not args.no_keyterms,
        )
    )

    if not committed:
        log.error("geen enkel segment vastgezet")
        return 1
    log.info("%s segment(en) vastgezet", len(committed))
    print("\n--- volledige transcript ---")
    print(" ".join(committed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
