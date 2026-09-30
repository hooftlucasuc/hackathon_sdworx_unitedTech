# Backend (rol B): van GitHub naar Cloud Run

Elke push naar `main` die iets in `backend/` wijzigt, bouwt automatisch een nieuwe image en deployt die naar Cloud Run in `europe-west1`. Alles hieronder draai je in **Cloud Shell** (knop rechtsboven in de GCP-console): daar staan `gcloud`, `git` en Python al klaar.

## 0. Eenmalig: repo op GitHub

Lokaal, vanuit de repo-root (de remote `origin` staat al ingesteld):

```bash
git add -A
git commit -m "Backend CallSight: webhook, Firestore, scoring, Cloud Run"
git push -u origin main
```

Controleer vooraf met `git status` dat er geen `.env` of `sa-key.json` tussen zit. De `.gitignore` sluit ze uit.

## 1. Eenmalig: GCP inrichten

In Cloud Shell:

```bash
git clone https://github.com/hooftlucasuc/hackathon_sdworck_unitedTech.git
cd hackathon_sdworck_unitedTech
GCP_PROJECT=<jouw-project-id> ./infra/gcp_setup.sh
```

Het script is idempotent. Het maakt of controleert:

| Onderdeel | Naam |
|---|---|
| Firestore Native | `(default)` in `europe-west1` |
| Artifact Registry | `callsight` (docker) |
| Runtime service account | `callsight-backend`: Firestore en Vertex AI |
| Deploy service account | `callsight-deployer`: Cloud Run deployen, images pushen |
| Secret | `elevenlabs-webhook-secret`, met een placeholder tot A het echte secret heeft |
| Indexen | vector-index op `solutions` en `calls`, plus twee history-indexen op `calls` |

## 2. Eenmalig: kennisbank vullen

Zonder oplossingen in `solutions` krijgt elke call nul suggesties. Laad de voorbeelddata, en later D's seed-data op dezelfde manier:

```bash
cd backend
pip install --user -e .
export GCP_PROJECT=<jouw-project-id>
python -m app.cli check                                    # embedding + Firestore bereikbaar?
python -m app.cli load-solutions samples/solutions.json
```

Historische calls van D laden op dezelfde manier, na de oplossingen:

```bash
python -m app.cli load-calls ../data/seed/calls.json
```

Het formaat staat in `TEAMPLAN.md` §6. `check` faalt met een index-fout zolang de vector-index nog bouwt. Status bekijk je met `gcloud firestore indexes composite list`.

## 3. Eenmalig: GitHub koppelen en trigger maken

**Koppelen** in de console:

1. Ga naar **Cloud Build → Repositories** en kies het tabblad **2nd gen**.
2. Klik **Create host connection**: provider GitHub, regio `europe-west1`, naam `github`.
3. Autoriseer de Cloud Build GitHub-app en geef hem toegang tot `hackathon_sdworck_unitedTech`.
4. Klik **Link repository**, kies de connectie `github` en de repo.

**Trigger** via **Cloud Build → Triggers → Create trigger**:

| Veld | Waarde |
|---|---|
| Region | `europe-west1` |
| Event | Push to a branch, branch `^main$` |
| Source | 2nd gen, de gelinkte repo |
| Included files filter | `backend/**` en `infra/cloudbuild.backend.yaml` |
| Configuration | Cloud Build configuration file, pad `infra/cloudbuild.backend.yaml` |
| Service account | `callsight-deployer@<project>.iam.gserviceaccount.com` |

Of in één commando in Cloud Shell, nadat de repo gelinkt is:

```bash
P=<jouw-project-id>
gcloud builds triggers create github --name=callsight-backend --region=europe-west1 \
  --repository=projects/$P/locations/europe-west1/connections/github/repositories/hooftlucasuc-hackathon_sdworck_unitedTech \
  --branch-pattern='^main$' --build-config=infra/cloudbuild.backend.yaml \
  --included-files='backend/**,infra/cloudbuild.backend.yaml' \
  --service-account=projects/$P/serviceAccounts/callsight-deployer@$P.iam.gserviceaccount.com
```

Het repository-pad toont `gcloud builds repositories list --connection=github --region=europe-west1`.

## 4. Eerste deploy

Klik **Run** op de trigger, of push een wijziging in `backend/`. Na ongeveer 3 minuten:

```bash
URL=$(gcloud run services describe callsight-backend --region=europe-west1 --format='value(status.url)')
curl -s $URL/healthz
curl -s -X POST $URL/demo/simulate-call -H 'Content-Type: application/json' \
  --data @backend/samples/call_vakantiegeld.json
curl -s $URL/calls/latest | python3 -m json.tool | head -40
```

Verwacht: `created: true`, `suggestions: 5`, en bovenaan de vakantiegeld-oplossing met de hoogste score. De API-documentatie staat op `$URL/docs`.

## 5. Doorgeven aan het team

- **Aan A:** de webhook-URL is `$URL/webhooks/elevenlabs`. Zet in ElevenLabs alleen de transcription-webhook aan, niet de audio-webhook. Het webhook-secret dat ElevenLabs toont, zet je zo in GCP:

  ```bash
  printf '%s' 'wsec_...' | gcloud secrets versions add elevenlabs-webhook-secret --data-file=-
  ```

  Run daarna de trigger opnieuw, zodat een nieuwe revisie het secret oppikt.
- **Aan C:** `VITE_API_URL=$URL`. Staat het dashboard later op een andere origin, zet die in de trigger-substitutie `_FRONTEND_ORIGIN`, komma-gescheiden met `http://localhost:5173`.
- **Aan D:** seed-data laadt via `load-solutions` en `load-calls`, zie stap 2. Zo gebruiken seed en backend gegarandeerd dezelfde ID's, hetzelfde embedding-model en dezelfde task types. De escalatiedrempel stel je bij met de trigger-substitutie `_ESCALATION_THRESHOLD`, standaard 60.

## Vertex geblokkeerd? Lokale embeddings

Staat in de GCP-omgeving een org-policy die Vertex AI Gen AI blokkeert (`constraints/vertexai.allowedModels` op `denyAll`, zoals in sommige Qwiklabs-labs), dan werkt geen enkel Vertex-embeddingmodel. Draai de embeddings dan lokaal in de backend, zonder Vertex:

```bash
cd ~/hackathon_sdworck_unitedTech/backend
# torch alleen als CPU-versie (de standaard sleept ~3GB CUDA mee en vult de Cloud Shell-schijf)
pip cache purge || true
pip install --user --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
pip install --user --no-cache-dir "sentence-transformers>=2.7,<6"
export GCP_PROJECT=<project-id>
export EMBEDDING_PROVIDER=local
export EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
export EMBEDDING_DIM=384

# de vector-indexen staan op 768; zet ze op 384 (eenmalig)
cd ~/hackathon_sdworck_unitedTech && EMBEDDING_DIM=384 ./infra/recreate_vector_indexes.sh

cd backend
python -m app.cli check                  # downloadt het model eenmalig, embedt en telt
python -m app.cli load-solutions samples/solutions.json
```

`load-solutions` schrijft de vectoren en werkt ook terwijl de index nog bouwt; de zoekactie bij een call werkt zodra de 384-index `READY` is. De Cloud Build-config staat standaard al op de lokale provider (`_EMBEDDING_PROVIDER: local`, dim 384, 2Gi geheugen); waar Vertex wél mag, zet je die drie terug op `vertex` / `gemini-embedding-001` / `768` en draai je het indexscript met `EMBEDDING_DIM=768`.

## Lokaal draaien

Zonder GCP, met een in-memory store en de voorbeelddata:

```bash
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
STORE_BACKEND=memory DEMO_MODE=true ELEVENLABS_WEBHOOK_SECRET=dev uvicorn app.main:app --reload --port 8080
pytest
```

De in-memory store gebruikt een woord-hash in plaats van echte embeddings. De scores zijn dus niet representatief, de flow wel. Tegen de echte Firestore werk je lokaal na `gcloud auth application-default login` met `GCP_PROJECT` in `.env`.

## Wat de backend doet

1. **Webhook** controleert de `ElevenLabs-Signature` (HMAC-SHA256, maximaal 30 minuten oud) en weigert alles zonder geldig secret. Alleen `post_call_transcription` wordt verwerkt. Audio wordt nooit opgeslagen.
2. **Parsing** haalt de vijf Data Collection-velden op. Een ontbrekend veld wordt null. Bedrijfsnamen worden genormaliseerd, dus "Bakkerij Verhulst BV" en "bakkerij verhulst" zijn hetzelfde bedrijf.
3. **Opslag** schrijft call, beller en bedrijf in één Firestore-transactie. Dezelfde `conversation_id` twee keer levert geen dubbele call en geen dubbele tellers op.
4. **Suggesties** komen uit een Vertex-embedding van het probleem, een vector search op `solutions` en de score uit `CONTEXT.md`. Faalt de embedding of de search, dan wordt de call toch opgeslagen met `suggestions_status` op `embedding_error` of `search_error`.
5. **Escalatie:** elke call krijgt `escalate`, waar als er geen suggestie is of de beste score onder `ESCALATION_THRESHOLD` ligt.
6. **Resolve** verhoogt `times_used` en eventueel `times_successful` van de gekozen oplossing. Zo stijgt de score van wat werkt bij de volgende call.

## Problemen

| Symptoom | Oorzaak en oplossing |
|---|---|
| Build faalt op `iam.serviceAccounts.actAs` | Het deploy-account mist `serviceAccountUser` op het runtime-account. Draai `gcp_setup.sh` opnieuw. |
| Deploy faalt op `allUsers` / policy constraint | Een organisatie-policy verbiedt publieke Cloud Run-services. Vervang in `infra/cloudbuild.backend.yaml` `--allow-unauthenticated` door `--no-invoker-iam-check`. |
| `suggestions_status: search_error` | De vector-index op `solutions` bouwt nog of ontbreekt. Wacht, en draai daarna `python -m app.cli rescore <call_id>`. |
| `embedding_error` of een 404 op het model | `gemini-embedding-001` is niet beschikbaar in de regio voor dit project. Zet de substitutie `_EMBEDDING_MODEL` op `text-multilingual-embedding-002` en laad de oplossingen opnieuw met `load-solutions --reset --yes`. |
| Webhook geeft 401 | Het secret in Secret Manager verschilt van dat in ElevenLabs, of de nieuwe secret-versie is nog niet uitgerold. Voeg de juiste versie toe en run de trigger opnieuw. |
| Webhook geeft 503 | `ELEVENLABS_WEBHOOK_SECRET` is leeg in de service. Controleer `--set-secrets` in de Cloud Build-config. |
