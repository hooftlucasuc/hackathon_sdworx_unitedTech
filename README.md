# CallSight

**Tectonic Hackathon 2026 · SD Worx-challenge "Unlock the Knowledge Within: Find it. Understand it. Trust it."**

> **In short.** When an employer calls SD Worx with a payroll question, the consultant has seconds to find an answer they can rely on, while the knowledge base offers three: one recently reviewed, one without an owner, one that applies to another country. CallSight listens along to the call (the caller is informed) and recognises the caller, company and problem in real time. It shows the caller's history, the company's history and the best-matching solutions from the knowledge base. Every suggestion comes with the reason to trust it: a deterministic, explainable score built from semantic similarity, the success rate in past calls and recency. The knowledge base also records who owns each answer, when it was last reviewed, which country it applies to and which versions conflict. CallSight proposes the next question to ask, escalates to an expert when there is no strong match, and gets better with every resolved call. No audio is stored; the consultant always decides.

## Wat het doet

Een werkgever belt SD Worx en een consultant neemt op. CallSight luistert mee: het gesprek wordt live uitgeschreven en beller, bedrijf en probleem worden herkend. Het dashboard toont meteen:
- de historie van de beller en van het bedrijf;
- de best passende oplossingen uit de kennisbank;
- de vraag die de consultant nu best stelt.

Bij elke oplossing staat **waarom ze te vertrouwen is**. Heeft de kennisbank geen sterk antwoord, dan zegt CallSight dat en verwijst het door.

Er is ook een tweede ingang, met dezelfde backend en dezelfde score: een ElevenLabs-agent neemt zelf op en stuurt na het gesprek een ondertekende webhook ([`docs/elevenlabs-agent.md`](docs/elevenlabs-agent.md)).

## Het twijfelmoment dat we oplossen

| Vraag uit de challenge | Hoe CallSight ze beantwoordt |
|---|---|
| What is reliable? | Score met drie deelwaarden (gelijkenis, succesratio uit echte calls, recency), zichtbaar per oplossing: geen black box |
| What is current? | Per oplossing de eigenaar en de datum van de laatste review; verouderde en tegenstrijdige versies zijn gemarkeerd |
| What applies in this context? | Land per oplossing, tegenover het land van de klant |
| Where are the gaps? | Open calls zonder oplossing, en "geen sterke match, escaleer" |
| Who has relevant expertise? | Doorverwijzing naar de eigenaar van het domein |
| What should I ask next? | "Vraag nu": de doorvraag die het verschil maakt tussen de oplossingen bovenaan, gemarkeerd als AI-voorstel |
| Which company is this really? | Opzoeking in de KBO: één treffer, meerdere ("bevestig welk") of niet gevonden |

Elke afgehandelde call ("werkte" of "werkte niet") past de succesratio aan: de kennisbank leert van wat in de praktijk werkt.

## Architectuur

```
microfoon (consultant + beller) ── scripts/listen.html (A)
        │ audio
        ▼
ElevenLabs realtime spraak-naar-tekst ◄── eenmalige token via de collector; de API-key blijft op de server
        │ vastgezette zinnen
        ▼
scripts/segment_collector.py (A): transcript per gesprek, velden herkennen (standaard met regels)
        │ zelfde payload als de post-call webhook
        ▼
Cloud Run backend (B, FastAPI): beller, bedrijf en call opslaan, embedding (lokaal model), vector search, top 5 met score
        │
        ▼
Firestore (europe-west1) ── onSnapshot ──► dashboard (C, React): live transcript, "Vraag nu", historie, oplossingen

Tweede ingang: ElevenLabs-agent voert het gesprek ──► post-call webhook met HMAC ──► dezelfde backend
```

Score per oplossing: `100 × (0,60 × similarity + 0,25 × succesratio + 0,15 × recency)`. Deterministisch, zonder LLM in de score ([`TEAMPLAN.md`](TEAMPLAN.md) §1.5). De backend escaleert onder **80**; die drempel is gekalibreerd op de seed-data ([`docs/demo-script.md`](docs/demo-script.md), Kalibratie).

## Draaien

Vereisten: `gcloud`, `firebase` CLI, Python 3.11+, Node 20+, een ElevenLabs-account.

```bash
# 1. Google Cloud en Firebase (eenmalig)
gcloud auth login && gcloud auth application-default login && firebase login
GCP_PROJECT=<project-id> ./infra/gcp_setup.sh        # Firestore, Cloud Run, secrets, indexen
GCP_PROJECT=<project-id> ./infra/firebase_setup.sh   # web-app, security rules, anonieme login; toont VITE_FIREBASE_*
cp .env.example .env                                 # GCP_PROJECT en de ElevenLabs-waarden

# 2. Backend: lokaal zonder GCP; deployen gaat via een push naar main (Cloud Build, docs/backend.md)
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev,local]"
STORE_BACKEND=memory DEMO_MODE=true ELEVENLABS_WEBHOOK_SECRET=dev uvicorn app.main:app --reload --port 8080
cd ..

# 3. Fictieve dataset, via de backend-pipeline (zelfde ID's en embeddings als live calls)
export EMBEDDING_PROVIDER=local EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 EMBEDDING_DIM=384
python scripts/seed.py --check                       # valideren zonder GCP
python scripts/seed.py --reset --yes                 # Firestore vullen; toont de scores van de drie demo-scenario's

# 4. Dashboard: http://localhost:5173, of zonder backend http://localhost:5173/?bron=demo
cd frontend && npm install && cp .env.example .env.local && npm run dev

# 5. Meeluisteren: open daarna http://localhost:8600/ (ELEVENLABS_API_KEY in de omgeving, niet in de code)
pip install -r scripts/requirements.txt
python scripts/segment_collector.py --port 8600 --forward-url http://localhost:8080/demo/simulate-call
```

Tweede ingang en tests: de agentconfig staat in `docs/elevenlabs-agent.md` (`scripts/elevenlabs_setup.py`). Een ondertekende payload afspelen zonder gesprek: `python scripts/replay_webhook.py`. End-to-end: `python scripts/smoke_test.py`.

## Wat niet af is

- **Live-ingang in de backend.** De collector stuurt elke tussenstand naar `/demo/simulate-call`. Dat werkt alleen met `DEMO_MODE=true` en is dus bedoeld voor lokaal en de demo. In productie hoort hier een geauthenticeerde live-route of de HMAC-webhook, met `DEMO_MODE=false` op Cloud Run.
- **Doorvragen ("Vraag nu").** Het dashboard toont en verwerkt ze al. De backend genereert ze nog niet: in de demo komen ze uit demodata. Vertex AI is in het hackathonproject geblokkeerd, en daarom herkent de collector de velden standaard met regels.
- **Trust-signalen op het scherm.** Eigenaar, reviewdatum, land en tegenstrijdige versies staan per oplossing in Firestore, en de KBO-controle per bedrijf. Het dashboard toont ze nog niet.
- **Escalatiedrempel.** De backend gebruikt 80 (gekalibreerd). Het dashboard heeft nog een eigen drempel van 50 (`frontend/src/types.ts`); die twee moeten gelijk getrokken worden.
- **Spraak en telefonie.** Consultant en beller delen één microfoon. Telefonie (Twilio/SIP) is niet gekoppeld.
- **Herkomst van de gegevens.** Trust-signalen en KBO-treffers komen uit de seed. In productie komen ze uit het documentbeheer van SD Worx en uit een live KBO-opzoeking.
- **Login.** Voor de demo is dat een anonieme login. Productie vraagt SSO met rollen.

## Privacy en GDPR

- **Fictieve data.** Alle personen, bedrijven en experten in `data/seed/` zijn verzonnen; gelijkenis met bestaande personen of bedrijven is toevallig.
  - Eén uitzondering: United Consulting (de werkgever van het team) staat als klant in de seed, met een fictieve contactpersoon en verzonnen cases.
  - De fictieve bedrijfsnamen zijn gecontroleerd tegen de KBO Open Data (FOD Economie, snapshot 29-09-2026): geen enkele bestaat als onderneming. Van de KBO bewaren we alleen publieke gegevens van rechtspersonen, nooit van eenmanszaken.
  - De kennisbank is een illustratie en geen juridisch advies.
- **Transparantie.** De consultant meldt bij het begin van het gesprek dat een AI-assistent live meeschrijft. Het transcript bevat de woorden van de beller én van de consultant, dus ook medewerkers worden vooraf geïnformeerd.
- **Wat we bewaren.** Het transcript en de herkende velden (naam, bedrijf, probleem, categorie, urgentie). **Geen audio.** Namen en transcripten komen nooit in logregels.
- **Waar.** Firestore en Cloud Run draaien in `europe-west1`. De embeddings berekent de backend zelf met een lokaal meertalig model, dus probleemteksten gaan niet naar een extern AI-model.
- **Sleutels.** De browser krijgt nooit de ElevenLabs-key, alleen een eenmalige token die de collector aanvraagt.
- **Toegang.** De browser kan alleen lezen, en alleen na een Firebase-login; schrijven kan uitsluitend de backend. Voor de demo is die login anoniem: wie de URL van het dashboard heeft, kan de fictieve calls lezen. Voor productie hoort hier SSO van SD Worx met rollen, zodat alleen consultants hun eigen klanten zien.
- **Open punten voor productie:**
  - **ElevenLabs.** De PoC draait op de standaardomgeving van ElevenLabs in de VS, ook voor de realtime spraak-naar-tekst.
    - Productie vraagt een Enterprise-account met EU-residency plus Zero Retention Mode.
    - Ook dan moet je per integratie nagaan of er verwerking buiten de EU gebeurt: residency dekt alleen de opslag ([`docs/elevenlabs-payload-check.md`](docs/elevenlabs-payload-check.md) §5).
    - Daarnaast is een verwerkersovereenkomst nodig.
  - **Bewaartermijn.** Een termijn per veld (bijvoorbeeld het transcript 90 dagen) en een verwijderprocedure op verzoek.
  - **Rechtsgrond.** De uitvoering van de dienstverleningsovereenkomst met de werkgever.

## EU AI Act

- **Rol van de AI.** CallSight ondersteunt de consultant: de beller praat met een mens. De consultant beslist welke vraag hij stelt en welke oplossing hij gebruikt. Op het dashboard staan de doorvragen als "AI-voorstel".
- **Transparantie.**
  - Bij het meeluisteren informeert de consultant de beller, zoals de GDPR vraagt.
  - Bij de tweede ingang geldt art. 50 van de AI Act rechtstreeks, want daar praat de beller met de agent. Die zegt daarom in de eerste zin dat hij een automatische assistent is. Dat is sinds 2 augustus 2026 verplicht.
- **Risico.** CallSight neemt geen beslissingen over personen en beoordeelt geen werknemers. Dat is een bewuste ontwerpkeuze: transcripten worden **niet** gebruikt om consultants te monitoren of te evalueren. Anders zou het systeem onder de hoog-risicocategorie werkgelegenheid van bijlage III vallen.
- **Uitlegbaar en begrensd.** De score is deterministisch: drie deelwaarden en geen LLM. Onder de gekalibreerde drempel escaleert CallSight naar een expert in plaats van een antwoord te gokken.
- **Meetbaar per gesprek, bij de agent-ingang.** ElevenLabs beoordeelt elk gesprek op twee criteria:
  - `intake_compleet`: naam, bedrijf en probleem zijn verzameld;
  - `geen_advies`: de agent gaf geen inhoudelijk advies, bedrag of termijn, en herhaalde geen naam van een werknemer.

  Zie [`docs/elevenlabs-agent.md`](docs/elevenlabs-agent.md) §5.

## Security

Aikido-scan voor en na de fixes: `docs/aikido-before.png` en `docs/aikido-after.png`.

- **Webhook.** HMAC-SHA256 over de ruwe body, met een tijdstolerantie. Zonder secret weigert hij alles (fail closed).
- **Spraak-naar-tekst.** Een eenmalige token; de ElevenLabs-key staat alleen op de server.
- **Firestore.** De browser leest alleen, na login. Schrijven gebeurt enkel via de backend, met een service account met minimale rollen.
- **API.**
  - Elke ID wordt tegen een vast patroon gevalideerd.
  - CORS staat alleen open voor de dashboard-origin.
  - Secrets staan in Secret Manager.
  - Namen komen niet in de logs.
- **Dependencies.** De versies liggen vast (`backend/requirements.txt`, `frontend/package-lock.json`), zodat Aikido ze op kwetsbaarheden kan controleren.
- **Aikido-bevinding "SQL injection"** in `backend/app/pipeline.py`: vals alarm, want er is geen SQL en de backend gebruikt Firestore. De foutmelding is herschreven, zodat het patroon niet meer matcht.
- **Open punt.** `/demo/simulate-call` werkt alleen met `DEMO_MODE=true` en staat buiten de demo uit op Cloud Run.

## Team

Rol A · Voice, B · Backend, C · Dashboard, D · Data en demo. Zie [`TEAMPLAN.md`](TEAMPLAN.md).
