# CONTEXT — CallSight (SD Worx hackathon, Tectonic 2026)

Plak dit bestand als context in Claude Code, Cursor of Claude.ai vóór je aan je deel begint. Het is zelfstandig: alles wat je nodig hebt om binnen het contract te bouwen staat hier. Het volledige plan met tijdlijn en jouw persoonlijke prompt staat in `TEAMPLAN.md`.

## Wat we bouwen

Een klant belt SD Worx. Een ElevenLabs-spraakagent neemt op, voert een kort gesprek in het Nederlands en haalt eruit: **wie belt, van welk bedrijf, met welk probleem, hoe dringend**. Na het gesprek stuurt ElevenLabs een webhook naar onze backend op Google Cloud. Die slaat de call op, herkent beller en bedrijf, en zoekt in de kennisbank naar oplossingen voor gelijkaardige problemen, elk met een uitlegbare score. Het dashboard toont dit in realtime: beller-historie, bedrijfshistorie en de top-5 oplossingen.

Verhaal voor de jury: *nog voor de medewerker terugbelt, weet hij wie dit is, wat er eerder speelde en wat toen werkte. Elke afgehandelde call maakt de kennisbank beter.*

```
telefoon → ElevenLabs agent → post-call webhook → Cloud Run (FastAPI) → Firestore (europe-west1)
                                                        ↓ Vertex embeddings + score
                                                   Dashboard (React, realtime)
```

## Team

| Rol | Bouwt | Map |
|---|---|---|
| A · Voice | ElevenLabs-agent, data collection, webhook-config, replay-script | `docs/elevenlabs-agent.md`, `scripts/`, `samples/` |
| B · Backend | FastAPI op Cloud Run, webhook, Firestore, embeddings, score, API | `backend/`, `infra/` |
| C · Dashboard | React-dashboard, realtime Firestore, oplossingen met score | `frontend/` |
| D · Data en demo | GCP-setup, seed-dataset, demo-script, README, Aikido, integratietest | `data/seed/`, `scripts/seed.py`, `docs/`, `README.md` |

Iedereen werkt op dummy-data van de buurrol tot de koppeling er is. `POST /demo/simulate-call` is de vaste testingang: het dashboard hoeft nooit op een echt gesprek te wachten.

## Contract (wijzigt alleen na melding aan alle vier)

### Velden die de agent uit het gesprek haalt

`caller_name` · `company_name` · `problem` · `category` (één uit: `vakantiegeld`, `loonberekening`, `ziekte`, `dimona`, `maaltijdcheques`, `bedrijfswagen`, `ontslag`, `overig`) · `urgency` (`laag`, `midden`, `hoog`).

### Webhook ElevenLabs → backend

`POST /webhooks/elevenlabs`, header `ElevenLabs-Signature: t=<ts>,v0=<hmac>` (HMAC-SHA256 over `"<ts>.<body>"` met het webhook-secret). Wij lezen uit de payload: `data.conversation_id`, `data.transcript[]`, `data.metadata.start_time_unix_secs`, `data.metadata.call_duration_secs`, `data.analysis.transcript_summary`, `data.analysis.data_collection_results.<veld>.value`. Antwoord `200 {"call_id": "..."}` binnen 5 s.

### Firestore-collecties (Native mode, europe-west1)

```
callers/{caller_id}     caller_id = "<slug naam>--<company_id>", bv. sofie-janssens--bakkerij-verhulst
                        name, company_id, first_seen, last_seen, call_count
companies/{company_id}  company_id = slug(company_name) zonder rechtsvorm, bv. "Bakkerij Verhulst BV" → bakkerij-verhulst
                        name, sector, size, first_seen, last_seen, call_count, open_issues
calls/{call_id}         call_id = conversation_id
                        caller_id, company_id (beide null als de agent ze niet kon ophalen),
                        caller_name, company_name, started_at, received_at, duration_secs,
                        problem, category, urgency, summary, transcript[], status: open | resolved,
                        problem_embedding: Vector(768),
                        suggestions[ {solution_id, title, score, reasons: {similarity, success, recency}} ] (max 5),
                        best_score, escalate (true als best_score < ESCALATION_THRESHOLD of geen suggestie),
                        suggestions_status: ok | no_problem | embedding_error | search_error,
                        chosen_solution_id, solution_worked, resolved_at
solutions/{solution_id} title, problem_text, solution_text, category, times_used, times_successful,
                        last_used_at, source_call_id, problem_embedding: Vector(768)
```

Alle tijdstippen zijn Firestore-timestamps (UTC), zodat `orderBy('started_at')` werkt. De API geeft ze als ISO-strings en laat `problem_embedding` altijd weg.

### API

| Method | Path | Doet |
|---|---|---|
| POST | `/webhooks/elevenlabs` | call opslaan, beller/bedrijf upserten, suggestions berekenen |
| GET | `/calls/latest` | nieuwste call met suggestions |
| GET | `/calls/{call_id}` | één call |
| GET | `/callers/{caller_id}` | beller + zijn calls |
| GET | `/companies/{company_id}` | bedrijf + alle calls |
| GET | `/calls/{call_id}/suggestions` | top-5 met score en deelwaarden |
| POST | `/calls/{call_id}/resolve` | `{solution_id, worked}` → tellers bijwerken, status resolved |
| POST | `/demo/simulate-call` | zelfde body als de webhook, zonder signature, alleen met `DEMO_MODE=true` |

Het dashboard leest daarnaast rechtstreeks uit Firestore met `onSnapshot` (alleen lezen).

Details voor wie tegen de API bouwt:

- `/demo/simulate-call` geeft elke aanroep een nieuwe `conversation_id` (`demo-…`) en de huidige tijd, zodat één voorbeeldbestand meerdere calls oplevert. Met `?keep_id=true` blijven id en starttijd uit de payload behouden.
- `/calls/{id}/suggestions` geeft de opgeslagen score plus de actuele velden van de oplossing: `solution_text`, `problem_text`, `category`, `times_used`, `times_successful`, `last_used_at`.
- `/calls/{id}/resolve` geeft 404 bij een onbekende call of oplossing en 409 als de call al opgelost is.
- History-lijsten in `/callers/{id}` en `/companies/{id}` bevatten geen transcript en geen suggestions, nieuwste eerst.
- Is `API_KEY` gezet op de backend, dan vraagt elke route behalve de webhook en `/healthz` de header `X-API-Key`. Standaard staat dit uit.
- Voorbeeldpayloads en voorbeeldoplossingen staan in `backend/samples/`. De OpenAPI-docs staan op `<backend-url>/docs`.

### Score van een oplossing

```
score        = 100 × (0.60 × similarity + 0.25 × success_rate + 0.15 × recency)
similarity   = 1 − cosine_distance(call.problem_embedding, solution.problem_embedding)
success_rate = (times_successful + 1) / (times_used + 2)
recency      = 1 bij ≤ 90 dagen, 0 bij ≥ 730 dagen, lineair ertussen
```

Deterministisch, geen LLM in de score. De drie deelwaarden reizen mee naar het dashboard als uitleg.

### Env

```
GCP_PROJECT=            GCP_REGION=europe-west1     GOOGLE_APPLICATION_CREDENTIALS=./sa-key.json
EMBEDDING_MODEL=gemini-embedding-001               EMBEDDING_DIM=768
ELEVENLABS_API_KEY=     ELEVENLABS_AGENT_ID=        ELEVENLABS_WEBHOOK_SECRET=
DEMO_MODE=true          FRONTEND_ORIGIN=http://localhost:5173
```

## Stack en regels

- **Backend:** Python 3.11, FastAPI, pydantic v2, google-cloud-firestore, google-cloud-aiplatform. Cloud Run, min-instances 0. Alle Firestore-calls in één repository-bestand.
- **Embeddings:** Vertex AI `gemini-embedding-001`, 768 dims, task `RETRIEVAL_QUERY` voor de vraag en `RETRIEVAL_DOCUMENT` voor solutions. Fallback: `text-multilingual-embedding-002`.
- **Dashboard:** Vite + React + TypeScript, Firebase JS SDK voor realtime lezen, `fetch` naar de API voor schrijven. Rustige stijl: antracietgrijze tekst, lichtgrijze panelen, één accentkleur voor de score. Geen UI-framework nodig.
- **Code:** type hints overal, `logging` in plaats van `print`, `pathlib` voor paden, pydantic `max_length` op alle vrije tekst, CORS alleen op `FRONTEND_ORIGIN`.
- **Secrets:** alleen in `.env` (lokaal) of Secret Manager (Cloud Run). `.env`, `sa-key.json` en `*.pem` staan in `.gitignore`. Nooit een key in code, commit of screenshot.
- **Privacy:** gespreksdata is persoonsgegevens. Alleen fictieve bellers en bedrijven, ook in seed-data en video. Geen audio bewaren, alleen transcript en geëxtraheerde velden. Nooit een naam of transcript in een logregel. Opslag uitsluitend `europe-west1`.
- **Geen extra features** buiten dit contract vóór de feature freeze (2:30). Iets wat ontbreekt: melden, niet zelf uitbreiden.

## Stand van de repo

- **Backend (B) staat:** `backend/` bevat de volledige FastAPI-app, 39 groene tests, een Dockerfile en `infra/cloudbuild.backend.yaml` voor automatische deploy naar Cloud Run bij elke push naar `main`. Opzet en koppeling met GitHub: `docs/backend.md`.
- **GCP-setup:** `infra/gcp_setup.sh` is de CallSight-versie. Het maakt Firestore, Artifact Registry, beide service accounts, het webhook-secret en alle indexen. D hoeft dit niet opnieuw te schrijven.
- **Seed-data van D** laadt met `python scripts/seed.py --reset --yes`, via `load_solutions` en `load_calls` van de backend. `--check` valideert zonder GCP, `--probe` scoort de drie demo-scenario's. Details: `TEAMPLAN.md` §6.
- **Restanten van het eerdere TrustCard-plan** (`BUILD_SPEC.md`, `countries/`, `sources/`) staan nog in de root en zijn niet de huidige koers. Ze gaan weg bij de freeze.

## Gedeelde taken

Punten die tussen de rollen vallen staan met eigenaar en status in `TEAMPLAN.md` §6. Nog open:

- **D:** `infra/firebase_setup.sh` draaien (script klaar) en de `VITE_FIREBASE_*`-config aan C geven.
- **C:** anonieme Firebase-login in het dashboard; de rules (klaar, `infra/firestore.rules`) laten lezen toe na login en schrijven nooit.
- **C en D:** hosting van het dashboard, daarna de origin in `_FRONTEND_ORIGIN` van de backend-trigger.
- **D:** IAM voor alle vier, billing en een budget-alert, in het eerste halfuur.
- **D:** de escalatiedrempel kalibreren op de seed-data, via `_ESCALATION_THRESHOLD`.
- **Team:** beslissen vóór de freeze of `resolve` ook een nieuwe oplossing mag aanmaken.
- **D:** de TrustCard-bestanden verwijderen bij de freeze.

Al klaar: de composite indexes, het webhook-secret in Secret Manager, de gedeelde `slug()` en embedder, en de `escalate`-vlag. D laadt seed-data met `python scripts/seed.py`, dat `load_solutions` en `load_calls` aanroept, zodat seed en live calls dezelfde ID's en embeddings krijgen.

## Demo-scenario's (D schrijft ze uit, A oefent ze)

1. **Terugkerende beller:** derde keer over vakantiegeld → historie vult zich, topscore > 85.
2. **Nieuw persoon, bekend bedrijf:** beller-historie leeg, bedrijfshistorie vol, oplossing hergebruikt.
3. **Onbekend probleem:** scores < 50, dashboard toont "geen sterke match, escaleer".

## Open punten

- Exacte veldnamen van de ElevenLabs post-call payload en de signature-header: A controleert tegen de actuele docs en meldt afwijkingen aan B.
- ElevenLabs verwerkt audio standaard buiten de EU; EU-residency is een productievoorwaarde, staat in de README als open punt.
- Telefoonnummer (Twilio/SIP) alleen als er tijd over is; een browser-testgesprek volstaat voor de demo.
