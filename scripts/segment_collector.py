#!/usr/bin/env python3
"""Verzamelt transcriptsegmenten, haalt er de vijf velden uit en duwt die naar de backend.

Dit is het stuk tussen de luisteraar en de tool. Elke keer dat `scribe_listen.py` een
segment vastzet, komt dat hier binnen, groeit de lopende transcript, en gaat er een
bijgewerkte payload naar de backend. Zo staat het antwoord er terwijl de vraag nog
gesteld wordt, in plaats van na afloop.

    python scripts/segment_collector.py --port 8600 --forward-url http://localhost:8080/demo/simulate-call
    python scripts/scribe_listen.py --audio ... --push-url http://localhost:8600/segment

Routes:
    POST /segment   {call_id, speaker, text}   een vastgezet stuk transcript
    GET  /state     de huidige stand van alle gesprekken
    GET  /state/<call_id>

De payload die naar de backend gaat heeft exact de vorm uit TEAMPLAN §1.2, zodat B's
webhook-parser en `/demo/simulate-call` ongewijzigd blijven. Alleen de bron verandert:
niet meer een afgelopen gesprek van een pratende agent, maar een lopend gesprek.

De extractie kent twee smaken:
  --extractor rules   deterministisch, geen credentials nodig, goed genoeg voor de demo
  --extractor gemini  de echte, via google-genai; vereist GCP_PROJECT en ADC
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("segment_collector")

REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_PROBLEM_CHARS = 400

CATEGORY_KEYWORDS = {
    "vakantiegeld": ["vakantiegeld", "vakantieattest", "vertrekvakantiegeld"],
    "loonberekening": ["brutoloon", "nettoloon", "bedrijfsvoorheffing", "rsz", "index", "barema", "loonberekening", "loonbrief"],
    "ziekte": ["ziek", "ziekte", "gewaarborgd loon", "arbeidsongeschikt", "ziekteattest"],
    "dimona": ["dimona", "dmfa", "aangifte", "in dienst", "uit dienst gemeld"],
    "maaltijdcheques": ["maaltijdcheque", "ecocheque", "cadeaucheque"],
    "bedrijfswagen": ["bedrijfswagen", "tankkaart", "voordeel alle aard", "mobiliteitsbudget"],
    "ontslag": ["ontslag", "opzegtermijn", "verbrekingsvergoeding", "c4", "outplacement"],
}
URGENCY_HIGH = ["dringend", "vandaag", "morgen", "urgent", "meteen", "spoed"]
URGENCY_MID = ["deze week", "loonrun", "volgende week", "snel"]


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


# --------------------------------------------------------------------------- extractie


def extract_rules(transcript: str) -> Dict[str, Optional[str]]:
    """Deterministische extractie. Geen model, geen credentials, geen verrassingen.

    Bedoeld als vangnet: het haalt de gevallen eruit waarin de beller zich normaal
    voorstelt ("met X van Y"). Lukt dat niet, dan blijven de velden leeg en dat is
    eerlijker dan raden.
    """
    lowered = transcript.lower()

    # Per zin zoeken, nooit over de hele transcript: anders loopt "van <Bedrijf>."
    # door tot in de volgende zin en wordt het bedrijf "Bakkerij Verhulst BV. Een".
    sentences_raw = [s.strip() for s in re.split(r"(?<=[.!?])\s+", transcript) if s.strip()]

    name = None
    company = None
    for sentence in sentences_raw:
        match = re.search(
            r"\bmet\s+([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){0,2})\s+van\s+([A-Z][\w'&-]*(?:\s+[A-Z][\w'&-]*){0,3})",
            sentence,
        )
        if match:
            name, company = match.group(1).strip(), match.group(2).strip(" .,")
            break
    if name is None:
        for sentence in sentences_raw:
            only_name = re.search(r"\b(?:met|ik ben|u spreekt met)\s+([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){0,2})", sentence)
            if only_name:
                name = only_name.group(1).strip()
                break
    if company is None:
        for sentence in sentences_raw:
            only_company = re.search(r"\bvan\s+([A-Z][\w'&-]*(?:\s+[A-Z][\w'&-]*){0,3})", sentence)
            if only_company:
                company = only_company.group(1).strip(" .,")
                break

    category = "overig"
    for name_, needles in CATEGORY_KEYWORDS.items():
        if any(needle in lowered for needle in needles):
            category = name_
            break

    urgency = "midden"
    if any(word in lowered for word in URGENCY_HIGH):
        urgency = "hoog"
    elif any(word in lowered for word in URGENCY_MID):
        urgency = "midden"

    # Het probleem: de eerste zin die een categoriewoord bevat, anders de langste zin.
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", transcript) if s.strip()]
    problem = None
    for sentence in sentences:
        low = sentence.lower()
        if any(needle in low for cat in CATEGORY_KEYWORDS.values() for needle in cat):
            problem = sentence
            break
    if problem is None and sentences:
        problem = max(sentences, key=len)

    return {
        "caller_name": name,
        "company_name": company,
        "problem": (problem or "")[:MAX_PROBLEM_CHARS] or None,
        "category": category,
        "urgency": urgency,
    }


def extract_gemini(transcript: str) -> Dict[str, Optional[str]]:
    """De echte extractie. Vereist GCP_PROJECT en application default credentials.

    De beschrijvingen zijn dezelfde als die van de data-collection velden in
    docs/elevenlabs-agent.md; ze zijn alleen verhuisd van de agentconfig naar hier,
    omdat Scribe geen analysestap heeft.
    """
    from google import genai  # lokaal geïmporteerd: alleen nodig voor deze smaak
    from google.genai import types

    project = os.environ.get("GCP_PROJECT")
    if not project:
        raise RuntimeError("GCP_PROJECT ontbreekt")
    client = genai.Client(vertexai=True, project=project, location=os.environ.get("GCP_REGION", "europe-west1"))

    schema = {
        "type": "OBJECT",
        "properties": {
            "caller_name": {"type": "STRING", "nullable": True},
            "company_name": {"type": "STRING", "nullable": True},
            "problem": {"type": "STRING", "nullable": True},
            "category": {"type": "STRING", "enum": list(CATEGORY_KEYWORDS) + ["overig"]},
            "urgency": {"type": "STRING", "enum": ["laag", "midden", "hoog"]},
        },
        "required": ["category", "urgency"],
    }
    prompt = (
        "Je krijgt de lopende transcript van een telefoongesprek waarin een Belgische werkgever "
        "een payrollvraag stelt aan SD Worx. Haal er vijf velden uit.\n\n"
        "caller_name: de naam van de persoon die belt, niet van een werknemer die genoemd wordt. "
        "Onbekend? Laat leeg.\n"
        "company_name: het bedrijf waarvoor hij belt, met rechtsvorm als die genoemd is. Nooit 'SD Worx'.\n"
        "problem: een zin in het Nederlands, derde persoon, met onderwerp, aanleiding en periode. "
        "Geen bedragen, rijksregisternummers of namen van werknemers; schrijf 'een bediende'.\n"
        "category: precies een uit de lijst.\n"
        "urgency: hoog bij vandaag of morgen of een dreigende deadline, midden bij deze week of de "
        "volgende loonrun, laag zonder deadline. Niets gezegd? midden.\n\n"
        "Het gesprek loopt nog; wat er niet in staat, laat je leeg.\n\n"
        f"Transcript:\n{transcript}"
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0,
        ),
    )
    return json.loads(response.text)


EXTRACTORS = {"rules": extract_rules, "gemini": extract_gemini}


# --------------------------------------------------------------------------- state


class Call:
    def __init__(self, call_id: str) -> None:
        self.call_id = call_id
        self.started_at = int(time.time())
        self.segments: List[Dict[str, str]] = []
        self.fields: Dict[str, Optional[str]] = {}
        self.updates = 0

    def transcript_text(self, speaker: Optional[str] = "beller") -> str:
        parts = [s["text"] for s in self.segments if speaker is None or s["speaker"] == speaker]
        return " ".join(parts)

    def payload(self) -> Dict[str, Any]:
        """De vorm uit TEAMPLAN §1.2, zodat B's parser ongewijzigd blijft."""
        now = int(time.time())
        return {
            "type": "post_call_transcription",
            "event_timestamp": now,
            "data": {
                "agent_id": "callsight_listener",
                "conversation_id": self.call_id,
                "status": "in_progress",
                "transcript": [
                    {
                        "role": "user" if s["speaker"] == "beller" else "agent",
                        "message": s["text"],
                        "time_in_call_secs": s["at"] - self.started_at,
                    }
                    for s in self.segments
                ],
                "metadata": {
                    "start_time_unix_secs": self.started_at,
                    "call_duration_secs": now - self.started_at,
                },
                "analysis": {
                    "call_successful": "unknown",
                    "transcript_summary": self.fields.get("problem") or "",
                    "data_collection_results": {
                        key: {"data_collection_id": key, "value": value, "rationale": "live extractie"}
                        for key, value in self.fields.items()
                    },
                },
            },
        }


class Collector:
    def __init__(self, extractor_name: str, forward_url: Optional[str]) -> None:
        self.extract = EXTRACTORS[extractor_name]
        self.extractor_name = extractor_name
        self.forward_url = forward_url
        self.calls: Dict[str, Call] = {}
        self.lock = threading.Lock()

    def add_segment(self, call_id: str, speaker: str, text: str) -> Dict[str, Any]:
        with self.lock:
            call = self.calls.setdefault(call_id, Call(call_id))
            call.segments.append({"speaker": speaker, "text": text, "at": int(time.time())})
            before = dict(call.fields)
            try:
                call.fields = self.extract(call.transcript_text("beller"))
            except Exception as exc:  # noqa: BLE001 - extractie mag het luisteren niet breken
                log.error("extractie mislukt: %s", exc)
                return {"call_id": call_id, "error": "extraction failed"}
            call.updates += 1
            changed = {k: v for k, v in call.fields.items() if before.get(k) != v}
            payload = call.payload()

        log.info(
            "%s segment %s | categorie=%s urgentie=%s | gewijzigd: %s",
            call_id,
            len(call.segments),
            call.fields.get("category"),
            call.fields.get("urgency"),
            ", ".join(changed) or "niets",
        )
        if self.forward_url:
            self.forward(payload)
        return {"call_id": call_id, "fields": call.fields, "changed": list(changed)}

    def forward(self, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.forward_url, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                log.debug("doorgestuurd: HTTP %s", response.status)
        except Exception as exc:  # noqa: BLE001
            log.warning("doorsturen mislukt: %s", exc)


def make_handler(collector: Collector):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: Any) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:  # noqa: N802
            if self.path.rstrip("/") != "/segment":
                self._send(404, {"error": "unknown route"})
                return
            length = int(self.headers.get("content-length", 0))
            try:
                payload = json.loads(self.rfile.read(length))
                call_id = str(payload["call_id"])
                speaker = str(payload.get("speaker", "beller"))
                text = str(payload["text"]).strip()
            except (ValueError, KeyError) as exc:
                self._send(400, {"error": f"bad body: {exc}"})
                return
            if not text:
                self._send(200, {"ignored": "empty"})
                return
            self._send(200, collector.add_segment(call_id, speaker, text))

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.rstrip("/")
            if path == "":
                page = Path(__file__).with_name("listen.html")
                data = page.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/token":
                # De browser krijgt nooit de API-key: een single-use token vervalt na
                # 15 minuten en wordt bij gebruik verbruikt.
                api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
                if not api_key:
                    self._send(503, {"error": "ELEVENLABS_API_KEY ontbreekt"})
                    return
                request = urllib.request.Request(
                    "https://api.elevenlabs.io/v1/single-use-token/realtime_scribe",
                    data=b"",  # zonder body antwoordt de API met 411 Length Required
                    method="POST",
                )
                request.add_header("xi-api-key", api_key)
                try:
                    with urllib.request.urlopen(request, timeout=15) as response:
                        self._send(200, json.loads(response.read()))
                except Exception as exc:  # noqa: BLE001
                    log.error("token ophalen mislukt: %s", exc)
                    self._send(502, {"error": "token ophalen mislukt"})
                return
            if path == "/state":
                with collector.lock:
                    self._send(
                        200,
                        {
                            "extractor": collector.extractor_name,
                            "calls": {
                                cid: {"fields": c.fields, "segments": len(c.segments), "updates": c.updates}
                                for cid, c in collector.calls.items()
                            },
                        },
                    )
                return
            if path.startswith("/state/"):
                call_id = path[len("/state/") :]
                with collector.lock:
                    call = collector.calls.get(call_id)
                    if not call:
                        self._send(404, {"error": "unknown call"})
                        return
                    self._send(200, {"fields": call.fields, "transcript": call.transcript_text(None)})
                return
            self._send(404, {"error": "unknown route"})

        def log_message(self, *args) -> None:  # stil: we loggen zelf
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8600)
    parser.add_argument("--extractor", default="rules", choices=sorted(EXTRACTORS))
    parser.add_argument("--forward-url", default=None, help="POST elke bijgewerkte payload hierheen")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    load_env(REPO_ROOT / ".env")

    collector = Collector(args.extractor, args.forward_url)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(collector))
    log.info(
        "luistert op http://127.0.0.1:%s/segment (extractor=%s, doorsturen naar %s)",
        args.port,
        args.extractor,
        args.forward_url or "niets",
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("gestopt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
