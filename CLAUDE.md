# CallSight (SD Worx hackathon)

Een klant belt SD Worx; een ElevenLabs-agent luistert mee, haalt naam, bedrijf en probleem uit het gesprek, en het dashboard toont meteen de beller-historie, bedrijfshistorie en de best scorende oplossingen.

## Status
Fase: opzet
Laatst bijgewerkt: 2026-09-30
Eigenaar: Lucas Hooft (team van vier, zie `TEAMPLAN.md` §2)

## Security
Gevoeligheid: **4** — gespreksdata is persoonsgegevens (naam beller, stem, werkgever, probleemomschrijving). Secrets (ElevenLabs API key, webhook-secret, GCP service-account key) zijn niveau 5 en staan alleen in `.env` / Secret Manager.
Maatregelen: fictieve data in de PoC (uitzondering: United Consulting als bestaand klantbedrijf, met verzonnen cases); geen audio bewaard, alleen transcript + geëxtraheerde velden; geen namen of transcripten in logs; webhook met HMAC-signature; opslag uitsluitend `europe-west1`; CORS alleen op de dashboard-origin.
Secrets: via omgevingsvariabelen lokaal, Secret Manager op Cloud Run, nooit in de code. `.gitignore` sluit `.env`, `sa-key.json` en `*.pem` uit.

## Stack
- Python 3.11 + FastAPI op Cloud Run — webhook-ontvanger en API, min-instances 0.
- Firestore Native (europe-west1) — documentmodel plus ingebouwde vector search, geen server.
- Vertex AI `gemini-embedding-001` (768 dims) — meertalige embeddings van probleemteksten.
- ElevenLabs Conversational AI — spraakagent met Data Collection en post-call webhook.
- Vite + React + TypeScript — dashboard, realtime via Firestore `onSnapshot`.

## Structuur
- `CONTEXT.md` — zelfstandig contextbestand voor teammates in Claude Code of Cursor. Eerst lezen.
- `TEAMPLAN.md` — het contract (§1), tijdlijn en prompts per teammate.
- `backend/app/` — FastAPI-app (rol B): `webhook.py`, `api.py`, `pipeline.py` (parsing, ids, suggesties), `scoring.py`, `store.py` (enige plek met Firestore-calls), `embeddings.py`, `cli.py`.
- `backend/samples/` — fictieve oplossingen en drie ElevenLabs-voorbeeldpayloads.
- `frontend/` — dashboard (rol C).
- `infra/` — `gcp_setup.sh` (GCP, rol B), `firebase_setup.sh` en `firestore.rules` (dashboard-toegang, rol D), `cloudbuild.{backend,listener,frontend}.yaml` (Cloud Run), `deploy_cloudrun.sh` (alle drie parallel), Firestore-indexen.
- `data/seed/` + `scripts/` — fictieve dataset en seed/replay-scripts (rollen A en D).
- `docs/` — ElevenLabs-agentconfig, demo-script, integratielog, Aikido-screenshots.

## Werkafspraken
- Het contract in `TEAMPLAN.md` §1 wijzigt alleen na melding aan alle vier.
- Pydantic-modellen met `max_length` op vrije tekst; `logging`, geen `print`; `pathlib` voor paden.
- Elke rol werkt op dummy-data van de buurrol tot de koppeling er is; `/demo/simulate-call` is de vaste testingang.
- Geen echte personen of bedrijven in seed-data, screenshots of video. Enige uitzondering: United Consulting als klantbedrijf in de seed, met fictieve contactpersoon Lindsey Tafels en verzonnen cases.

## Commando's
```
installeren:  cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
              cd frontend && npm install
draaien:      cd backend && STORE_BACKEND=memory DEMO_MODE=true ELEVENLABS_WEBHOOK_SECRET=dev uvicorn app.main:app --reload --port 8080
              cd frontend && npm run dev
seed:         python scripts/seed.py --reset --yes     (demo-dataset uit data/seed/, via de backend-pipeline)
              cd backend && python -m app.cli load-solutions samples/solutions.json   (alleen B's voorbeeldoplossingen)
testen:       cd backend && pytest && ruff check app tests
deployen:     ./infra/deploy_cloudrun.sh in Cloud Shell (backend, luisteraar, dashboard), of push naar main (trigger), zie docs/backend.md
```

## Verwijzingen
- `TEAMPLAN.md` — contract, tijdlijn, prompts; open bij elke wijziging aan datamodel of API.
- `docs/backend.md` — open bij deployen, GitHub koppelen, secrets wisselen of een deployfout.
- `docs/demo-script.md` — de drie demo-scenario's en Lindsey's beurten (rol D).
- `docs/video-script.md` — scènes, timing en voice-over van de video (rol D).

## Wijzigingslog
| Datum | Wat veranderde | Gevolg voor architectuur of security |
|---|---|---|
| 2026-09-30 | Start als TrustCard (kennis-trust-score); country-profielen, core-, store- en ingest-laag geschreven | Gevoeligheid 5 door API-keys; secrets via env |
| 2026-09-30 | Pivot naar CallSight: ElevenLabs-gesprek → GCP → dashboard; `TEAMPLAN.md` met contract en prompts | Gevoeligheid blijft 4/5 maar nu door persoonsgegevens uit gesprekken: GDPR-sectie verplicht in README, geen audio-opslag, EU-residency van ElevenLabs is een open punt |
| 2026-09-30 | Backend rol B gebouwd: webhook met HMAC, Firestore-transacties, Vertex-embeddings via google-genai, score, alle routes, Cloud Build-deploy vanaf GitHub; TrustCard-modules uit `backend/` verwijderd | Twee service accounts met minimale rollen (runtime en deployer); webhook-secret in Secret Manager, fail closed zonder secret; geen audio of namen in logs; Cloud Run publiek voor de webhook, optionele `API_KEY` voor de overige routes |
| 2026-09-30 | Gedeelde taken toegevoegd (`TEAMPLAN.md` §6); backend kreeg `escalate`-vlag met `ESCALATION_THRESHOLD` en `load-calls` voor historische seed-calls | Open securitypunt: Firestore rules en Firebase Auth voor het dashboard, anders zijn calls met persoonsgegevens publiek leesbaar |
| 2026-09-30 | Seed-data met trust-signalen (land, eigenaar, reviewdatum, conflicten); United Consulting als klant met fictieve contactpersoon Lindsey Tafels | Eén bestaand bedrijf in een publieke repo: alleen verzonnen cases, geen echte payrollgegevens |
| 2026-09-30 | Luisteraar als eigen Cloud Run-service (`/medewerker`, `/beller`); dashboard kan zonder Firebase via `VITE_DATA_SOURCE=api` (pollt de REST-API); builds met BuildKit-cache en model-laag vóór de code | ElevenLabs API-key in Secret Manager (`elevenlabs-api-key`), nooit in de browser (single-use token). Open punt: `/token` en `/state` van de luisteraar zijn publiek, dus iedereen met de URL kan tokens op onze credits halen en transcripten lezen; credit limit op de key en services weghalen na de demo |
