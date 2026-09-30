#!/usr/bin/env python3
"""Maakt of update de CallSight-intake-agent bij ElevenLabs vanuit de config hieronder.

De agent is hiermee reproduceerbaar: wie de config wil kennen leest dit bestand, niet
het dashboard. De inhoud volgt docs/elevenlabs-agent.md; wijzigt daar iets, dan wijzigt
het hier mee.

    python scripts/elevenlabs_setup.py                 # aanmaken, of updaten als ELEVENLABS_AGENT_ID gezet is
    python scripts/elevenlabs_setup.py --dry-run       # toont de request-body, praat niet met de API
    python scripts/elevenlabs_setup.py --agent-id X    # update die agent

Het agent_id gaat naar stdout, alle logging naar stderr. Zo kan:

    ELEVENLABS_AGENT_ID=$(python scripts/elevenlabs_setup.py)

Alleen stdlib, zodat dit draait op elke laptop in het team zonder venv of pip install.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("elevenlabs_setup")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://api.elevenlabs.io"
# ElevenLabs' eigen default. Let op: de oude default voices verlopen 31-12-2026.
FALLBACK_VOICE_ID = "cjVigY5qzO86Huf0OWal"
TIMEOUT_SECS = 30

AGENT_NAME = "CallSight intake NL"

FIRST_MESSAGE = (
    "Goeiedag, u spreekt met de automatische assistent van SD Worx. "
    "Ik neem uw vraag op zodat een collega u kan terugbellen. Waarmee kan ik u helpen?"
)

SYSTEM_PROMPT = """# Rol
Je bent de telefonische intake-assistent van SD Worx. Je bent een AI en je doet
nooit alsof je een medewerker bent. Je spreekt Nederlands, beleefd en to the point,
en je spreekt de beller aan met u.

# Doel
Je neemt een inkomende oproep aan van een werkgever met een payrollvraag. Je hebt
een taak: vaststellen wie belt, van welk bedrijf, wat het probleem is en hoe
dringend het is. Een menselijke collega belt daarna terug met de oplossing.

# Wat je nooit doet
- Je geeft geen advies, geen berekening, geen inschatting en geen inhoudelijk
  antwoord, ook niet als de beller aandringt. Je zegt dan: "Daar kan ik u zelf niet
  mee verder helpen, maar ik zorg dat de juiste collega u terugbelt."
- Je herhaalt geen loonbedragen, rijksregisternummers, rekeningnummers of
  geboortedata die de beller noemt.
- Je herhaalt geen namen van werknemers, ex-werknemers of andere derden. Je spreekt
  over "een bediende", "een werknemer", "iemand die uit dienst ging".
- Je vraagt niet naar gegevens die je niet nodig hebt: geen rijksregisternummer,
  geen klantnummer, geen rekeningnummer.
- Je belooft geen termijn, geen bedrag en geen uitkomst.

# Verloop
Houd het gesprek onder de zes eigen beurten.
1. Begroet, zeg dat je de automatische assistent van SD Worx bent, vraag waarmee je
   kunt helpen.
2. Laat de beller het probleem uitleggen. Onderbreek niet. Stel hoogstens een
   verduidelijkende vraag, en alleen als je echt niet begrijpt waar het over gaat.
3. Vraag naam en bedrijf als de beller die niet uit zichzelf gegeven heeft, samen in
   een zin: "Met wie spreek ik, en voor welk bedrijf belt u?"
4. Vat het probleem samen in een zin en vraag of dat klopt. Begin met "Als ik het
   goed begrijp: ". Verbetert de beller je, neem dan zijn formulering over.
5. Vraag hoe dringend het is: "Moet dit vandaag opgelost zijn, deze week, of kan het
   wachten?"
6. Sluit af: bevestig dat een collega terugbelt, bedank, en beeindig het gesprek met
   de end_call-tool.

# Als iets ontbreekt
- Geeft de beller zijn naam of bedrijf niet, vraag het een keer opnieuw. Weigert hij,
  ga door zonder. Blijf niet aandringen.
- Is het probleem na twee pogingen nog onduidelijk, noteer wat je wel hebt en sluit af.
- Gaat de vraag niet over payroll, zeg dat je enkel payrollvragen aanneemt en sluit af.

# Toon
Korte zinnen. Geen jargon, geen opsommingen, geen "uiteraard" of "absoluut". Klink als
iemand die efficient een formulier invult, niet als een verkoper."""

CATEGORIES = [
    "vakantiegeld",
    "loonberekening",
    "ziekte",
    "dimona",
    "maaltijdcheques",
    "bedrijfswagen",
    "ontslag",
    "overig",
]

URGENCIES = ["laag", "midden", "hoog"]

# De beschrijving stuurt de extractie; de veldnaam doet niets. Elke beschrijving zegt
# wat we wel willen, wat we niet willen, en wat er moet gebeuren als het ontbreekt.
DATA_COLLECTION: Dict[str, Dict[str, Any]] = {
    "caller_name": {
        "type": "string",
        "description": (
            "De volledige naam van de persoon die belt, zoals hij of zij die zelf opgeeft. Alleen de beller "
            "zelf, niet de naam van een werknemer, ex-werknemer of collega die in het gesprek ter sprake komt. "
            'Geef voornaam en achternaam in normale spelling, zonder aanspreking: "Sofie Janssens", niet '
            '"mevrouw Janssens". Noemt de beller geen naam, laat dit veld dan leeg.'
        ),
    },
    "company_name": {
        "type": "string",
        "description": (
            "De naam van het bedrijf of de organisatie waarvoor de beller belt, inclusief de rechtsvorm als "
            'die genoemd wordt (BV, NV, VZW, CV). Nooit "SD Worx": dat is de partij die opneemt, niet de '
            "klant. Noemt de beller enkel een handelsnaam of een afkorting, neem dan letterlijk over wat hij "
            "zegt. Wordt er geen bedrijf genoemd, laat dit veld dan leeg."
        ),
    },
    "problem": {
        "type": "string",
        "description": (
            "Een zin in het Nederlands die beschrijft welk concreet probleem of welke vraag de beller heeft, "
            "geformuleerd in de derde persoon. Neem het onderwerp, de aanleiding en de periode mee als die "
            'genoemd zijn. Voorbeeld: "Het vakantiegeld van een bediende die in maart uit dienst ging klopt '
            'niet." Neem geen bedragen, rijksregisternummers, rekeningnummers, geboortedata of namen van '
            'werknemers op: schrijf "een bediende" of "een werknemer". Is er geen duidelijk probleem '
            "uitgesproken, laat dit veld dan leeg."
        ),
    },
    "category": {
        "type": "string",
        "enum": CATEGORIES,
        "description": (
            "De categorie waarin het probleem van de beller valt. Kies er precies een. "
            '"vakantiegeld": enkel of dubbel vakantiegeld, vertrekvakantiegeld, vakantieattest. '
            '"loonberekening": fouten in bruto- of nettoloon, bedrijfsvoorheffing, RSZ, index, barema. '
            '"ziekte": gewaarborgd loon, arbeidsongeschiktheid, ziekteattest, langdurig zieken. '
            '"dimona": Dimona-aangiften, DmfA, in- en uitdienstmeldingen. '
            '"maaltijdcheques": maaltijd-, eco- en cadeaucheques. '
            '"bedrijfswagen": bedrijfswagens, tankkaarten, voordeel alle aard, mobiliteitsbudget. '
            '"ontslag": opzegtermijn, verbrekingsvergoeding, C4, outplacement. '
            'Kies "overig" alleen wanneer geen enkele andere categorie past.'
        ),
    },
    "urgency": {
        "type": "string",
        "enum": URGENCIES,
        "description": (
            "Hoe dringend de beller het probleem vindt, op basis van wat hij zegt over de termijn. "
            '"hoog": het moet vandaag of morgen opgelost zijn, er dreigt een wettelijke deadline of een '
            'loonrun, of de beller zegt zelf dat het dringend is. "midden": het moet deze week of voor de '
            'volgende loonrun. "laag": het kan wachten, of het is een vraag zonder deadline. Zegt de beller '
            'niets over dringendheid, kies dan "midden".'
        ),
    },
}

EVALUATION_CRITERIA: List[Dict[str, Any]] = [
    {
        "id": "intake_compleet",
        "name": "intake_compleet",
        "type": "prompt",
        "conversation_goal_prompt": (
            "De intake is geslaagd wanneer de assistent aan het eind van het gesprek drie dingen heeft: de "
            "naam van de beller, de naam van zijn bedrijf, en een concreet omschreven probleem. Geef "
            '"success" wanneer alle drie aanwezig zijn, ook als de samenvatting kort was. Geef "failure" '
            "wanneer een van de drie ontbreekt."
        ),
    },
    {
        "id": "geen_advies",
        "name": "geen_advies",
        "type": "prompt",
        "conversation_goal_prompt": (
            'Controleer of de assistent zich aan zijn beperking gehouden heeft. Geef "failure" wanneer de '
            "assistent inhoudelijk advies gaf, een bedrag of berekening noemde, een termijn of uitkomst "
            "beloofde, of een loonbedrag, rijksregisternummer of de naam van een werknemer herhaalde. Geef in "
            'alle andere gevallen "success".'
        ),
    },
]

# Zonder deze boost komen Dimona, DmfA en C4 er regelmatig verminkt uit, en dan mist de
# extractie de categorie.
ASR_KEYWORDS = [
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


def build_config(voice_id: str, name: str = AGENT_NAME) -> Dict[str, Any]:
    """De volledige body voor create; update stuurt dezelfde structuur als patch."""
    return {
        "name": name,
        "tags": ["hackathon", "callsight"],
        "conversation_config": {
            "agent": {
                "language": "nl",
                "first_message": FIRST_MESSAGE,
                "prompt": {
                    "prompt": SYSTEM_PROMPT,
                    "llm": "gemini-2.5-flash",
                    "temperature": 0.2,
                    "built_in_tools": {
                        "end_call": {
                            "name": "end_call",
                            "type": "system",
                            "params": {"system_tool_type": "end_call"},
                        }
                    },
                },
            },
            # eleven_flash_v2 (de default) is Engels-only; nl vraagt v2_5 of multilingual_v2.
            "tts": {
                "model_id": "eleven_flash_v2_5",
                "voice_id": voice_id,
                "stability": 0.5,
                "speed": 1.0,
            },
            "asr": {"provider": "scribe_realtime", "quality": "high", "keywords": ASR_KEYWORDS},
            "turn": {"turn_timeout": 7, "turn_eagerness": "normal"},
            # De zes-beurtenlimiet is promptwerk; dit is de enige harde vangrail.
            "conversation": {"max_duration_seconds": 180},
        },
        "platform_settings": {
            "summary_language": "nl",
            "analysis_llm": "gemini-2.5-flash",
            "data_collection": DATA_COLLECTION,
            "evaluation": {"criteria": EVALUATION_CRITERIA},
        },
    }


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


def call_api(method: str, url: str, api_key: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("xi-api-key", api_key)
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECS) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:2000]
        # Nooit de key mee loggen; die zit in de header, niet in detail, maar wees expliciet.
        raise SystemExit(f"{method} {url} gaf HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"{method} {url} onbereikbaar: {exc.reason}") from exc
    return json.loads(payload) if payload else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agent-id", help="update deze agent in plaats van er een aan te maken")
    parser.add_argument("--name", default=AGENT_NAME, help=f"agentnaam (default: {AGENT_NAME})")
    parser.add_argument("--voice-id", help="overschrijft ELEVENLABS_VOICE_ID")
    parser.add_argument("--base-url", default=None, help=f"API-basis (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--dry-run", action="store_true", help="toon de body, praat niet met de API")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    load_env(REPO_ROOT / ".env")

    voice_id = args.voice_id or os.environ.get("ELEVENLABS_VOICE_ID") or FALLBACK_VOICE_ID
    if voice_id == FALLBACK_VOICE_ID:
        log.warning("ELEVENLABS_VOICE_ID niet gezet, val terug op de ElevenLabs-default (Engelstalige stem)")
    config = build_config(voice_id, args.name)

    if args.dry_run:
        print(json.dumps(config, indent=2, ensure_ascii=False))
        return 0

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        log.error("ELEVENLABS_API_KEY ontbreekt (zet hem in .env of in je omgeving)")
        return 2

    base_url = (args.base_url or os.environ.get("ELEVENLABS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    agent_id = args.agent_id or os.environ.get("ELEVENLABS_AGENT_ID", "").strip()

    if agent_id:
        log.info("agent %s bijwerken", agent_id)
        call_api("PATCH", f"{base_url}/v1/convai/agents/{agent_id}", api_key, config)
    else:
        log.info("nieuwe agent aanmaken")
        created = call_api("POST", f"{base_url}/v1/convai/agents/create", api_key, config)
        agent_id = created.get("agent_id", "")
        if not agent_id:
            log.error("API gaf geen agent_id terug")
            return 1
        log.info("aangemaakt; zet ELEVENLABS_AGENT_ID=%s in .env", agent_id)

    print(agent_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
