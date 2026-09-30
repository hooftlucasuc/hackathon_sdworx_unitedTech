# CallSight (SD Worx hackathon)

Een klant belt SD Worx; een ElevenLabs-agent luistert mee, haalt naam, bedrijf en probleem uit het gesprek, en het dashboard toont meteen de beller-historie, bedrijfshistorie en de best scorende oplossingen.

## Status
Fase: opzet
Laatst bijgewerkt: 2026-09-30
Eigenaar: Lucas Hooft (team van vier, zie `TEAMPLAN.md` §2)

## Security
Gevoeligheid: **4** — gespreksdata is persoonsgegevens (naam beller, stem, werkgever, probleemomschrijving). Secrets (ElevenLabs API key, webhook-secret, GCP service-account key) zijn niveau 5 en staan alleen in `.env` / Secret Manager.
Maatregelen: alleen fictieve data in de PoC; geen audio bewaard, alleen transcript + geëxtraheerde velden; geen namen of transcripten in logs; webhook met HMAC-signature; opslag uitsluitend `europe-west1`; CORS alleen op de dashboard-origin.
Secrets: via omgevingsvariabelen lokaal, Secret Manager op Cloud Run, nooit in de code. `.gitignore` sluit `.env`, `sa-key.json` en `*.pem` uit.

## Stack
- Python 3.11 + FastAPI op Cloud Run — webhook-ontvanger en API, min-instances 0.
- Firestore Native (europe-west1) — documentmodel plus ingebouwde vector search, geen server.
- Vertex AI `gemini-embedding-001` (768 dims) — meertalige embeddings van probleemteksten.
- ElevenLabs Conversational AI — spraakagent met Data Collection en post-call webhook.
- Vite + React + TypeScript — dashboard, realtime via Firestore `onSnapshot`.

## Structuur
- `TEAMPLAN.md` — het contract (§1), rolverdeling en prompts per teammate. Eerst lezen.
- `backend/` — FastAPI-app (rol B). Bevat nog restanten van het vorige TrustCard-plan, zie `TEAMPLAN.md` §5.
- `frontend/` — dashboard (rol C).
- `infra/` — `gcp_setup.sh`, Firestore-indexen, Cloud Run deploy.
- `data/seed/` + `scripts/` — fictieve dataset en seed/replay-scripts (rollen A en D).
- `docs/` — ElevenLabs-agentconfig, demo-script, integratielog, Aikido-screenshots.
- `countries/`, `BUILD_SPEC.md` — vorig plan; verwijderen bij de feature freeze.

## Werkafspraken
- Het contract in `TEAMPLAN.md` §1 wijzigt alleen na melding aan alle vier.
- Pydantic-modellen met `max_length` op vrije tekst; `logging`, geen `print`; `pathlib` voor paden.
- Elke rol werkt op dummy-data van de buurrol tot de koppeling er is; `/demo/simulate-call` is de vaste testingang.
- Nooit echte personen of bedrijven in seed-data, screenshots of video.

## Commando's
```
installeren:  cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
              cd frontend && npm install
draaien:      cd backend && uvicorn app.main:app --reload   |   cd frontend && npm run dev
seed:         python scripts/seed.py --reset
testen:       cd backend && pytest
```

## Verwijzingen
- `TEAMPLAN.md` — contract, tijdlijn, prompts; open bij elke wijziging aan datamodel of API.
- `docs/demo-script.md` — de drie demo-scenario's (rol D).

## Wijzigingslog
| Datum | Wat veranderde | Gevolg voor architectuur of security |
|---|---|---|
| 2026-09-30 | Start als TrustCard (kennis-trust-score); country-profielen, core-, store- en ingest-laag geschreven | Gevoeligheid 5 door API-keys; secrets via env |
| 2026-09-30 | Pivot naar CallSight: ElevenLabs-gesprek → GCP → dashboard; `TEAMPLAN.md` met contract en prompts | Gevoeligheid blijft 4/5 maar nu door persoonsgegevens uit gesprekken: GDPR-sectie verplicht in README, geen audio-opslag, EU-residency van ElevenLabs is een open punt |
