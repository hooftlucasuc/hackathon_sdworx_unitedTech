# CallSight — teamplan (SD Worx track)

Pitch in één zin: **een klant belt SD Worx, de AI luistert mee, en nog tijdens het gesprek staat op het dashboard wie belt, wat de geschiedenis is en welke oplossing het best past.**

Flow:

```
telefoon ──► ElevenLabs agent ──► post-call webhook ──► Cloud Run (FastAPI) ──► Firestore (europe-west1)
                (luistert, haalt                              │                        │
                 naam/bedrijf/probleem                        ▼                        ▼
                 uit het gesprek)                   Vertex embeddings +        Dashboard (React, realtime)
                                                    similarity-score           beller · bedrijf · oplossingen
```

Vier bouwers, elk één laag. Het **contract** in §1 is de enige gedeelde afspraak: wie zich daaraan houdt, hoeft niet op de anderen te wachten. Elke rol kan met dummy-data van de andere rol werken tot de koppeling er is.

---

## 1. Contract (gedeeld, niet wijzigen zonder het aan alle vier te melden)

### 1.1 Wat ElevenLabs uit het gesprek haalt (Data Collection velden op de agent)

| Veld | Type | Voorbeeld |
|---|---|---|
| `caller_name` | string | "Sofie Janssens" |
| `company_name` | string | "Bakkerij Verhulst BV" |
| `problem` | string | "Vakantiegeld van een bediende die in maart uit dienst ging klopt niet" |
| `category` | string, één uit lijst | `vakantiegeld` · `loonberekening` · `ziekte` · `dimona` · `maaltijdcheques` · `bedrijfswagen` · `ontslag` · `overig` |
| `urgency` | string | `laag` · `midden` · `hoog` |

### 1.2 Webhook: ElevenLabs → backend

`POST https://<cloud-run-url>/webhooks/elevenlabs`, header `ElevenLabs-Signature: t=<ts>,v0=<hmac>` (HMAC-SHA256 van `"<ts>.<body>"` met het webhook-secret). Body is de standaard ElevenLabs post-call payload; wij gebruiken alleen:

```json
{
  "type": "post_call_transcription",
  "data": {
    "conversation_id": "conv_abc123",
    "agent_id": "agent_xyz",
    "status": "done",
    "transcript": [{"role": "user", "message": "…", "time_in_call_secs": 3}],
    "metadata": {"start_time_unix_secs": 1760000000, "call_duration_secs": 184},
    "analysis": {
      "transcript_summary": "…",
      "data_collection_results": {
        "caller_name": {"value": "Sofie Janssens"},
        "company_name": {"value": "Bakkerij Verhulst BV"},
        "problem": {"value": "…"},
        "category": {"value": "vakantiegeld"},
        "urgency": {"value": "hoog"}
      }
    }
  }
}
```

Backend antwoordt `200 {"call_id": "..."}` binnen 5 s (verwerking daarna asynchroon als nodig).

### 1.3 Firestore-collecties (Native mode, `europe-west1`)

```
callers/{caller_id}          caller_id = slug(caller_name + company_id)
  name, company_id, first_seen, last_seen, call_count, phone_hash (optioneel)

companies/{company_id}       company_id = slug(company_name)
  name, sector, size, first_seen, last_seen, call_count, open_issues

calls/{call_id}              call_id = conversation_id van ElevenLabs
  caller_id, company_id, started_at, duration_secs, problem, category, urgency,
  summary, transcript (list), status: open | resolved,
  problem_embedding: Vector(768),
  suggestions: [ {solution_id, score, reasons: {similarity, success, recency}} ]   ← max 5
  chosen_solution_id (null tot een agent kiest)

solutions/{solution_id}      kennisbank van eerdere problemen + oplossingen
  title, problem_text, solution_text, category, times_used, times_successful,
  last_used_at, source_call_id (null bij seed), problem_embedding: Vector(768)
```

`calls` en `solutions` dragen beide een `problem_embedding` zodat Firestore vector search werkt zonder join.

### 1.4 API van de backend (voor het dashboard)

| Method | Path | Geeft |
|---|---|---|
| POST | `/webhooks/elevenlabs` | ontvangt call, schrijft caller/company/call, berekent suggestions |
| GET | `/calls/latest` | de meest recente call met suggestions (voor het live-scherm) |
| GET | `/calls/{call_id}` | één call, volledig |
| GET | `/callers/{caller_id}` | caller + zijn calls (nieuwste eerst) |
| GET | `/companies/{company_id}` | company + alle calls van alle bellers |
| GET | `/calls/{call_id}/suggestions` | top-5 oplossingen met score en uitleg |
| POST | `/calls/{call_id}/resolve` | body `{solution_id, worked: true/false}` → update `times_used/successful`, `status=resolved` |
| POST | `/demo/simulate-call` | zelfde body als 1.2 zonder signature, alleen met `DEMO_MODE=true` — zodat het dashboard nooit op ElevenLabs hoeft te wachten |

Het dashboard mag óók rechtstreeks Firestore lezen met `onSnapshot` (realtime); de API is er voor schrijven en voor de score.

### 1.5 Score van een oplossing (deterministisch, uitlegbaar)

```
score = 100 × (0.60 × similarity + 0.25 × success_rate + 0.15 × recency)

similarity   = 1 − cosine_distance(call.problem_embedding, solution.problem_embedding)
success_rate = (times_successful + 1) / (times_used + 2)          # Laplace, nooit 0/0
recency      = 1 als last_used_at ≤ 90 dagen, 0 bij ≥ 730 dagen, lineair ertussen
```

Filter: zelfde `category` krijgt +0 maar een andere category wordt niet uitgesloten (categorisatie door de agent is feilbaar). Elke suggestie draagt de drie deelwaarden mee, het dashboard toont ze als uitleg.

### 1.6 Env (`.env.example`)

```
GCP_PROJECT=
GCP_REGION=europe-west1
GOOGLE_APPLICATION_CREDENTIALS=./sa-key.json
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIM=768
ELEVENLABS_API_KEY=
ELEVENLABS_AGENT_ID=
ELEVENLABS_WEBHOOK_SECRET=
DEMO_MODE=true
FRONTEND_ORIGIN=http://localhost:5173
```

---

## 2. Rollen en tijdlijn (4 u)

| Tijd | A · Voice (ElevenLabs) | B · Backend (GCP) | C · Dashboard | D · Data, integratie, demo |
|---|---|---|---|---|
| 0:00–0:30 | agent aangemaakt, system prompt, 5 data-collection velden, testgesprek in browser werkt | repo `backend/`, FastAPI skelet, Firestore + Vertex auth werkt, `/demo/simulate-call` schrijft een call | Vite + React scaffold, Firestore SDK, layout met 4 panelen op dummy JSON | `infra/gcp_setup.sh`, `.env.example`, seed-dataset ontwerpen (10 bedrijven, 25 bellers, 40 solutions, 60 oude calls) |
| 0:30–1:30 | webhook ingesteld naar ngrok/Cloud Run URL, payload gelogd, signature-check getest | webhook-endpoint met HMAC, upsert caller/company/call, embedding + vector search + score | live-scherm (laatste call), caller-historie, company-historie, oplossingen met score | `seed.py` draait, README, GDPR-sectie, Aikido-baseline |
| 1:30–2:30 | agent-prompt tunen: kort, vraagt naam + bedrijf uit zichzelf, vat probleem samen, spreekt NL | `/calls/*`, `/callers/*`, `/companies/*`, `/resolve`; Cloud Run deploy | realtime `onSnapshot` op `calls`, auto-navigatie naar nieuwe call, uitleg-tooltips bij score | end-to-end: echt gesprek → dashboard binnen 10 s; scores tunen op de seed-data |
| 2:30 | **feature freeze** | | | |
| 2:30–3:15 | 3 demo-gesprekken oefenen (script in §4) | bugfixes, logging, Aikido-findings | polish live-scherm | video-script, Aikido rescan, Builderbase-tekst |
| 3:15–4:00 | opname | opname-support | opname | montage, inleveren |

Afhankelijkheden: C heeft B's `/demo/simulate-call` nodig vanaf 0:30 (B doet dat eerst). D's seed-data is nodig voor B's score-test vanaf 1:00 en voor C's historie-panelen. A is onafhankelijk tot 0:30, daarna heeft A een publieke URL van B nodig (ngrok volstaat tot Cloud Run staat).

---

## 3. Prompts per teammate

Elke prompt is zelfstandig: plak hem in Claude Code of Cursor samen met `TEAMPLAN.md`. De eerste regel van elke prompt is de instructie om §1 als contract te lezen.

### Prompt A · Voice / ElevenLabs

```
Lees eerst TEAMPLAN.md §1 (contract). Jij bouwt de ElevenLabs-kant van CallSight, een hackathon-PoC voor SD Worx.

Doel: een ElevenLabs Conversational AI agent die inbound gesprekken van klanten (Belgische werkgevers met een payroll-vraag) aanneemt, in het Nederlands, en aan het eind van het gesprek via de post-call webhook de velden uit §1.1 oplevert.

Lever op:
1. docs/elevenlabs-agent.md met exact: agent-naam, system prompt, first message, taal nl, stem, de 5 Data Collection velden (naam, type, beschrijving die ElevenLabs gebruikt om het veld uit de transcript te halen — schrijf die beschrijving zorgvuldig, dat is wat de extractie stuurt), evaluation criteria (call_successful: heeft de agent naam, bedrijf en probleem?), webhook-URL en waar het webhook-secret staat.
2. De system prompt zelf: de agent stelt zich voor als SD Worx assistent, vraagt naam en bedrijf als de beller die niet spontaan geeft, laat de beller het probleem uitleggen, herhaalt het probleem in één zin ter bevestiging, vraagt hoe dringend het is, en sluit af met "een collega belt u terug". Maximum 6 beurten. Geen advies geven, alleen inventariseren. De agent mag nooit loonbedragen of persoonsgegevens van derden herhalen.
3. scripts/elevenlabs_setup.py: maakt of update de agent via de ElevenLabs API (agents endpoint) vanuit een config-dict, zodat de agent reproduceerbaar is. API key uit env ELEVENLABS_API_KEY. Print het agent_id.
4. scripts/replay_webhook.py: stuurt een opgeslagen post-call payload (samples/postcall_*.json) met correcte ElevenLabs-Signature header naar een URL, zodat B en C zonder echt gesprek kunnen testen. Bewaar 3 echte payloads van je testgesprekken in samples/.
5. Instelling van de post-call webhook in het ElevenLabs dashboard naar de URL van B (eerst ngrok, later Cloud Run). Documenteer in docs/elevenlabs-agent.md hoe je de URL wisselt.

Randvoorwaarden: Python 3.11, requests of httpx, geen secrets in code, logging in plaats van print. Controleer in de ElevenLabs docs de actuele naam van de data-collection en webhook-velden voor je iets hardcodeert; de payload in §1.2 is ons contract, wijk je af, meld dat aan B.

Test: een browser-testgesprek van 1 minuut levert een webhook-payload waarin alle 5 velden gevuld zijn.
```

### Prompt B · Backend / GCP

```
Lees eerst TEAMPLAN.md §1 (contract). Jij bouwt de backend van CallSight, een hackathon-PoC voor SD Worx: FastAPI op Cloud Run, Firestore + Vertex AI embeddings in europe-west1.

Lever op in backend/:
1. pyproject.toml (fastapi, uvicorn, pydantic, pydantic-settings, google-cloud-firestore, google-cloud-aiplatform, httpx; dev: pytest, ruff). Python 3.11.
2. app/config.py: Settings uit env volgens §1.6.
3. app/webhook.py: POST /webhooks/elevenlabs. Verifieer ElevenLabs-Signature (t=<ts>,v0=<hex>, HMAC-SHA256 over "<ts>.<raw body>" met ELEVENLABS_WEBHOOK_SECRET; weiger als ts ouder dan 30 min of hash fout → 401). Parse de payload uit §1.2; ontbrekende data_collection velden worden null, geen crash. Idempotent op conversation_id.
4. app/pipeline.py: process_call(payload) → upsert companies/{slug}, callers/{slug}, schrijf calls/{conversation_id}; embed het probleem met Vertex (gemini-embedding-001, 768 dims, task RETRIEVAL_QUERY; fallback text-multilingual-embedding-002); vector search op solutions (find_nearest, COSINE, limit 10); score volgens §1.5; sla top-5 suggestions met deelwaarden op in de call.
5. app/api.py: alle GET/POST routes uit §1.4. /demo/simulate-call accepteert dezelfde body zonder signature en alleen als DEMO_MODE=true. /resolve past times_used/times_successful aan en zet status=resolved.
6. app/store.py: één Firestore-repository met alle reads/writes; vector search in één functie. Geen Firestore-calls buiten dit bestand.
7. infra/Dockerfile + infra/deploy.sh (gcloud run deploy, region europe-west1, min-instances 0, secrets uit Secret Manager, CORS alleen FRONTEND_ORIGIN).
8. tests/test_signature.py (goede/foute/verlopen signature) en tests/test_score.py (score-formule met vaste getallen, deterministisch).

Regels: pydantic-modellen met max_length op vrije tekst; logging, geen print; nooit een transcript of naam in een logregel; secrets alleen via env. Firestore vector index: composite index op solutions.problem_embedding (dimension 768, flat), commando in infra/firestore.indexes.md.

Eerste 30 minuten: alleen /demo/simulate-call die een call in Firestore schrijft, zodat C kan beginnen. Daarna de rest.

Test: python scripts/replay_webhook.py (van A) of een curl naar /demo/simulate-call → binnen 5 s staat de call in Firestore met 5 suggestions en scores tussen 0 en 100.
```

### Prompt C · Dashboard

```
Lees eerst TEAMPLAN.md §1 (contract). Jij bouwt het dashboard van CallSight, een hackathon-PoC voor SD Worx: de medewerker ziet tijdens/na een inbound gesprek meteen wie belt, de geschiedenis, en de best passende oplossingen.

Stack: Vite + React + TypeScript, Firebase JS SDK (Firestore, alleen lezen, realtime onSnapshot), fetch naar de backend-API uit §1.4 voor schrijven. Geen UI-framework nodig; CSS-modules of plain CSS. Rustige stijl: antracietgrijze tekst, lichtgrijze panelen, één accentkleur voor de score.

Schermen:
1. /live — luistert met onSnapshot op calls (orderBy started_at desc, limit 1). Zodra een nieuwe call binnenkomt springt het scherm ernaartoe. Bovenaan: naam, bedrijf, category-badge, urgency-badge, probleem in één zin, samenvatting. Daaronder 3 panelen naast elkaar:
   - Beller-historie: alle vorige calls van deze caller_id (datum, probleem, status, gekozen oplossing).
   - Bedrijf-historie: alle calls van dit company_id door alle bellers, plus tellers (aantal calls, open issues).
   - Oplossingen: top-5 uit call.suggestions, gesorteerd op score, elk met grote score (0-100), titel, oplossingstekst, en een uitklapbare uitleg met de drie deelwaarden (similarity, success_rate, recency) als kleine balkjes. Knop "Gebruikt — werkte" / "Gebruikt — werkte niet" → POST /calls/{id}/resolve.
2. /calls/:id — dezelfde view voor een oudere call (via klik in de historie).
3. /companies/:id en /callers/:id — eenvoudige lijstpagina's.
4. Een "Simuleer gesprek"-knop (alleen zichtbaar als VITE_DEMO_MODE=true) die een van 3 vaste payloads naar POST /demo/simulate-call stuurt, zodat je zonder ElevenLabs kunt demonstreren.

Types: schrijf src/types.ts letterlijk naar §1.3. Data-access alleen in src/api/client.ts (REST) en src/api/firestore.ts (realtime). Env: VITE_API_URL, VITE_FIREBASE_* config, VITE_DEMO_MODE.

Eerste 30 minuten: layout op src/mock/call.json (maak die zelf volgens §1.3) zodat je niet op B wacht. Daarna overschakelen op Firestore.

Test: B's /demo/simulate-call aanroepen → binnen 2 s verschijnt de call op /live zonder refresh; klik op een oplossing → status verandert naar resolved in Firestore.
```

### Prompt D · Data, integratie, demo

```
Lees eerst TEAMPLAN.md §1 (contract). Jij zorgt voor de data, de infrastructuur, de integratietest en het demo-verhaal van CallSight, een hackathon-PoC voor SD Worx.

Lever op:
1. infra/gcp_setup.sh: enable firestore, aiplatform, run, secretmanager; Firestore Native in europe-west1; service account met datastore.user + aiplatform.user; vector index op solutions.problem_embedding (768, flat) en op calls.problem_embedding. Idempotent (|| true). .env.example volgens §1.6.
2. data/seed/: fictieve dataset, alles verzonnen, geen echte personen of bedrijven. 10 bedrijven (naam, sector, grootte), 25 bellers verdeeld over die bedrijven, 40 solutions in de 8 categorieën uit §1.1 (Belgische payroll-thema's: vakantiegeld bediende/arbeider, maaltijdcheques, Dimona-laattijdig, gewaarborgd loon bij ziekte, bedrijfswagen VAA, opzegtermijn, dertiende maand), elk met problem_text, solution_text en realistische times_used / times_successful. 60 historische calls verdeeld over de bellers zodat minstens 3 bellers en 3 bedrijven een zichtbare geschiedenis hebben. Als CSV of JSON, één bestand per collectie.
3. scripts/seed.py: leest data/seed/, embed problem_text via Vertex (zelfde model en task als B), schrijft naar Firestore. Vlag --reset wist de collecties eerst.
4. Drie demo-scenario's in docs/demo-script.md, letterlijk uitgeschreven wat de beller zegt (A oefent ze):
   a. Terugkerende beller: Sofie Janssens van Bakkerij Verhulst belt voor de derde keer over vakantiegeld → historie vult zich, topoplossing score > 85.
   b. Nieuw persoon, bekend bedrijf: iemand anders van hetzelfde bedrijf → beller-historie leeg, bedrijf-historie vol, oplossing hergebruikt.
   c. Nieuw probleem: iets wat niet in de kennisbank zit → lage scores (< 50), dashboard toont "geen sterke match, escaleer".
5. README.md: probleem → oplossing → architectuur-diagram (de flow bovenaan TEAMPLAN.md) → hoe draaien (gcp_setup, .env, seed, backend, dashboard, ElevenLabs-agent) → wat niet af is → GDPR-sectie: gespreksdata bevat persoonsgegevens (naam, stem, werkgever); in de PoC alleen fictieve data; opslag europe-west1; geen audio bewaard, alleen transcript + geëxtraheerde velden; ElevenLabs verwerkt audio buiten de EU tenzij EU-residency is ingesteld — productie vereist DPA, bewaartermijn per veld, en toestemmingsmelding aan het begin van het gesprek → EU AI Act: beperkt risico, transparantie (beller hoort dat een AI meeluistert), mens beslist (medewerker kiest de oplossing), geen automatische beslissing over personen.
6. Integratietest om 1:30: echt testgesprek van A → webhook van B → dashboard van C. Meet de tijd tussen ophangen en verschijnen op /live. Log wat fout gaat als issues in docs/integration-log.md.
7. Aikido: baseline-scan bij start (screenshot docs/aikido-before.png), rescan na freeze (docs/aikido-after.png).

Regels: geen echte persoonsgegevens, ook niet van teamleden, in seed-data of screenshots. Alle scripts Python 3.11, logging, geen print.
```

---

## 4. Demo-verhaal (3 min)

0:00–0:20 het probleem: een klant belt, de medewerker zoekt in drie systemen wie dit is en of dit al eerder speelde.
0:20–1:40 scenario a live: bellen, ophangen, dashboard vult zich, topoplossing met uitleg van de score.
1:40–2:20 scenario c: onbekend probleem, lage score, "escaleer" — het systeem doet niet alsof het het weet.
2:20–3:00 opslag in GCP, alles in europe-west1, geen audio bewaard; elke afgehandelde call maakt de kennisbank beter (times_successful stijgt, score volgt).

---

## 5. Wat van de eerdere TrustCard-opzet blijft

De TrustCard-modules in `backend/` zijn vervangen door de CallSight-backend (rol B, klaar, zie `docs/backend.md`). In de root staan nog `BUILD_SPEC.md`, `countries/` en `sources/` van het vorige plan; die gaan weg bij de freeze. `infra/gcp_setup.sh` is al de CallSight-versie, dus punt 1 van prompt D is gedaan.

---

## 6. Gedeelde taken die tussen de rollen vallen

Deze punten hoorden bij geen enkele rol. Eigenaar en status per punt; werk de status bij wanneer je er één afrondt.

| Wat | Waarom het nodig is | Eigenaar | Status |
|---|---|---|---|
| **Firebase aan het GCP-project koppelen**: web-app registreren, `VITE_FIREBASE_*`-config | C kan pas realtime lezen als die er is. | D, in de GCP-setup | **Script klaar, nog te draaien:** `infra/firebase_setup.sh` koppelt Firebase, registreert de web-app, rolt de rules uit en toont de `VITE_FIREBASE_*`-regels voor `frontend/.env.local`. |
| **Firestore security rules en Firebase Auth** | Zonder rules werkt `onSnapshot` niet, of staan alle calls publiek. Aikido en de jury zien dat. | D schrijft de rules, C bouwt de login | **Klaar** (`infra/firestore.rules`, teambeslissing): lezen na (anonieme) Firebase-login, schrijven nooit. `infra/firebase_setup.sh` zet anonieme login aan. Voor productie: SSO met rollen (README, Security). |
| **Composite indexes voor C's queries** | `calls where caller_id == X orderBy started_at desc` en hetzelfde met `company_id` falen zonder index. | D | **Klaar.** `infra/gcp_setup.sh` maakt ze, samen met de vector-indexen. |
| **Hosting van het dashboard** | CORS staat op localhost. Waar draait C's build in de video? | C bouwt, D zet Firebase Hosting op en past `FRONTEND_ORIGIN` aan | Hosting-config klaar in `firebase.json` (`frontend/dist`, SPA-rewrite); deploy-commando staat aan het eind van `infra/firebase_setup.sh`. De origin gaat in de trigger-substitutie `_FRONTEND_ORIGIN`, komma-gescheiden met `http://localhost:5173`, daarna de trigger opnieuw draaien. |
| **Secrets in Secret Manager** | B's deploy leest ze, maar niemand maakt ze aan. | D | **Aangemaakt.** `gcp_setup.sh` maakt `elevenlabs-webhook-secret` met een placeholder. Nog te doen: A's echte secret toevoegen, commando in `docs/backend.md` stap 5. |
| **Wie mag in het GCP-project**: IAM voor alle vier, billing, budget-alert | Het eerste halfuur mag niemand geblokkeerd zijn. | D, bij de start | Open. Minimaal: B en D `Editor`, A en C `Viewer` plus `Firebase Viewer`, en een budget-alert op het hackathonkrediet. |
| **Een gedeelde `slug()`** | De seed van D en de upsert van B moeten dezelfde ID's maken, anders vindt scenario 1 de historie niet. | B schrijft ze, `seed.py` importeert ze | **Klaar.** `company_id_for` en `caller_id_for` in `backend/app/pipeline.py`. `scripts/seed.py` laadt alles via `load_solutions` en `load_calls`, dus door exact dezelfde pipeline. |
| **Een gedeelde embedder** | De seed en de queries moeten met hetzelfde model, dezelfde task en dezelfde dimensie embedden. | Dezelfde module voor B en D | **Klaar.** `backend/app/embeddings.py`; oplossingen laden met `python -m app.cli load-solutions`. |
| **Een drempel voor "escaleer"** | C toont de melding, maar niemand bepaalt wanneer. | D kalibreert op de seed-data, B zet de vlag in de response | **B-deel klaar.** Elke call heeft `escalate`: waar als er geen suggestie is of de beste score onder `ESCALATION_THRESHOLD` ligt, standaard 60. D stelt de waarde bij via de trigger-substitutie `_ESCALATION_THRESHOLD`. |
| **Nieuwe oplossing uit een call** | Het juryverhaal ("elke call maakt de kennisbank beter") heeft geen route die het waarmaakt. | Beslissen vóór de freeze: B of niet | Open beslissing. Nu stijgen alleen de tellers van bestaande oplossingen. Voorstel: `resolve` accepteert ook een nieuwe oplossingstekst en maakt daarmee een `solutions`-document met `source_call_id`. Ongeveer een halfuur werk voor B. |
| **Opruimen van de TrustCard-bestanden bij de freeze** | Nu staat het er alleen als intentie. | D | Open. Verwijderen: `BUILD_SPEC.md`, `countries/`, `sources/` en de `sources`-regels in `.gitignore`. `backend/` is al opgeruimd. |

### Historische calls voor de seed (voor D)

**Stand:** `python scripts/seed.py --reset --yes` doet dit voor de demo-dataset. `data/seed/*.json` is D's bewerkformaat met relatieve datums (`days_ago`); `seed.py` zet dat om naar de payloads hieronder en naar `SolutionIn`, roept `load_solutions` en `load_calls` aan en schrijft daarna de velden bij die de pipeline niet kent (trust-signalen, sector, grootte, rol). Laad `data/seed/calls.json` dus niet rechtstreeks met de CLI.

`python -m app.cli load-calls <bestand>.json` verwacht een JSON-lijst van ElevenLabs post-call payloads, hetzelfde formaat als `backend/samples/call_*.json`, met een unieke `conversation_id` en een `start_time_unix_secs` in het verleden. Een optioneel veld per payload markeert de call als opgelost:

```json
"resolution": {"solution_id": "vakantiegeld-uitdienst-bediende", "worked": true, "resolved_at": "2026-06-01T10:00:00Z"}
```

Een resolution verhoogt `times_used` en `times_successful` van die oplossing. Tel die calls dus niet ook al mee in de tellers van `solutions.json`. Laad eerst de oplossingen, dan de calls.
