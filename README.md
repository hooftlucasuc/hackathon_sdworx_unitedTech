# CallSight

**Tectonic Hackathon 2026 · SD Worx-challenge "Unlock the Knowledge Within: Find it. Understand it. Trust it."**

Een klant belt SD Worx met een payrollvraag. Een spraakagent neemt op, vraagt wie belt, van welk bedrijf en wat het probleem is. Nog voor een medewerker terugbelt, toont CallSight de historie van de beller en het bedrijf, en de oplossingen die eerder werkten. Bij elk antwoord staat **waarom het te vertrouwen is**: wie het beheert, wanneer het werd nagekeken, hoe vaak het echt werkte en voor welk land het geldt. Het systeem toont ook wanneer het geen antwoord heeft en wie het wel weet.

## Het twijfelmoment dat we oplossen

Een medewerker vindt drie antwoorden op dezelfde vraag: één recent, één zonder eigenaar, één voor een ander land. CallSight maakt dat verschil zichtbaar in plaats van het te verbergen achter één samenvatting:

| Vraag uit de challenge | Hoe CallSight ze beantwoordt |
|---|---|
| What is reliable? | Score met drie deelwaarden (gelijkenis, succesratio uit echte calls, recency), geen black box |
| What is current? | Datum van laatste review en eigenaar per oplossing; verouderde versies worden gemarkeerd |
| What applies in this context? | Land per oplossing, vergeleken met het land van de klant |
| Where are the gaps? | Open calls zonder oplossing en "geen sterke match, escaleer" |
| Who has relevant expertise? | Doorverwijzing naar de eigenaar van het domein |
| Which company is this really? | Het bedrijf van de beller wordt opgezocht in de KBO: één treffer, meerdere treffers ("bevestig welk") of niet gevonden |

Elke afgehandelde call ("werkte" / "werkte niet") past de succesratio aan: de kennisbank leert van wat in de praktijk werkt.

## Architectuur

```
telefoon / browser ─► ElevenLabs-agent ─► post-call webhook (HMAC) ─► Cloud Run (FastAPI) ─► Firestore (europe-west1)
                                                                          │ embeddings (lokaal model)     │
                                                                          ▼ + vector search + score       ▼
                                                                                          Dashboard (React, realtime, login)
```

Score per oplossing: `100 × (0,60 × similarity + 0,25 × succesratio + 0,15 × recency)`. Deterministisch, geen LLM in de score. Details in [`TEAMPLAN.md`](TEAMPLAN.md) §1.5.

## Draaien

Vereisten: `gcloud`, `firebase` CLI, Python 3.11+, Node 20+, een ElevenLabs-account.

```bash
# 1. Google Cloud en Firebase (eenmalig)
gcloud auth login && gcloud auth application-default login && firebase login
GCP_PROJECT=<project-id> ./infra/gcp_setup.sh        # Firestore, Cloud Run, secrets, indexen (rol B)
GCP_PROJECT=<project-id> ./infra/firebase_setup.sh   # web-app, security rules; toont VITE_FIREBASE_*
cp .env.example .env                                 # vul GCP_PROJECT en de ElevenLabs-waarden in

# 2. Fictieve dataset (via de backend-pipeline, dus zelfde ID's en embeddings als live calls)
#    Zelfde embedding-instellingen als de backend op Cloud Run; nu lokaal, want Vertex Gen AI is in het project geblokkeerd:
#    export EMBEDDING_PROVIDER=local EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 EMBEDDING_DIM=384
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev,local]" && cd ..
python scripts/seed.py --check                       # valideren zonder GCP
python scripts/seed.py --reset --yes                 # Firestore vullen; toont ook de scores van de demo-scenario's
# optioneel: KBO-controle van de seed-bedrijven opnieuw maken (data/seed/kbo.json staat al in de repo)
python scripts/kbo_lookup.py <pad-naar>/KboOpenData_<nr>_<datum>_Full.zip


# 3. Backend
#    TODO rol B: commando's

# 4. Dashboard
#    TODO rol C: commando's

# 5. ElevenLabs-agent
#    zie docs/elevenlabs-agent.md (rol A)
```

Demo zonder telefoon: `POST /demo/simulate-call` met een payload uit `samples/`, of de knop "Simuleer gesprek" op het dashboard (alleen met `DEMO_MODE=true`, lokaal).

## Wat niet af is

- TODO: bijwerken bij de feature freeze.
- Telefoonnummer (Twilio/SIP): de demo gebruikt een browser-testgesprek.
- Trust-signalen komen uit de seed-data; in productie komen eigenaar en reviewdatum uit het documentbeheer van SD Worx.

## Privacy en GDPR

- **Fictieve data.** Alle personen, bedrijven en experten in `data/seed/` zijn verzonnen; gelijkenis met bestaande personen of bedrijven is toevallig. Eén uitzondering: United Consulting (de werkgever van het team) staat als klant in de seed, met een fictieve contactpersoon en verzonnen cases. De fictieve bedrijfsnamen zijn gecontroleerd tegen de KBO Open Data (snapshot 29-09-2026): geen enkele bestaat als onderneming, zodat er geen verzonnen problemen aan een echt bedrijf hangen. Bron van de KBO-gegevens: KBO Open Data, FOD Economie (snapshot 29-09-2026); daarvan bewaren we alleen publieke gegevens van rechtspersonen, nooit van eenmanszaken. De kennisbank is een illustratie en geen juridisch advies.
- **Wat we bewaren:** transcript en de geëxtraheerde velden (naam, bedrijf, probleem, categorie, urgentie). **Geen audio.** Namen en transcripten komen nooit in logregels.
- **Waar:** Firestore en Cloud Run draaien in `europe-west1`. De embeddings worden in de backend zelf berekend (lokaal meertalig model), dus probleemteksten gaan niet naar een extern AI-model.
- **Toegang:** de browser kan alleen lezen, en alleen na Firebase-login; schrijven kan uitsluitend de backend (Firestore security rules). Voor de demo is dat een anonieme login: wie de URL van het dashboard heeft, kan de fictieve calls lezen. Voor productie hoort hier SSO van SD Worx met rollen, zodat alleen consultants hun eigen klanten zien. De webhook weigert verzoeken zonder geldige HMAC-signature.
- **Open punten voor productie:**
  - De PoC draait op de standaard (VS) omgeving van ElevenLabs. Voor productie is een Enterprise-account met EU-residency plus Zero Retention Mode nodig, en dan nog moet per integratie worden nagegaan of er verwerking buiten de EU plaatsvindt: residency dekt de opslag, en de ElevenLabs-docs noemen post-call webhooks als uitzondering die tot verwerking buiten de regio kan leiden (zie `docs/elevenlabs-payload-check.md` §5). Daarnaast is een verwerkersovereenkomst nodig. De audio-webhook staat uit.
  - Bewaartermijn per veld (bijvoorbeeld transcript 90 dagen, geëxtraheerde velden zolang het klantdossier loopt) en een verwijderprocedure op verzoek.
  - Rechtsgrond: uitvoering van de dienstverleningsovereenkomst met de werkgever; de beller wordt aan het begin van het gesprek geïnformeerd.

## EU AI Act

- **Transparantie (art. 50):** de agent zegt in de eerste zin dat de beller met een AI-assistent praat. Deze verplichting geldt sinds 2 augustus 2026.
- **Risico:** het systeem vat een vraag samen en stelt oplossingen voor aan een medewerker. Het neemt geen beslissingen over personen, beoordeelt geen werknemers en valt daarmee niet onder de hoog-risicocategorieën van bijlage III.
- **Mens in de lus:** een medewerker kiest de oplossing en belt terug. De score is uitlegbaar (drie deelwaarden) en het systeem escaleert zelf wanneer het geen sterke match heeft.
- **Meetbaar per gesprek:** ElevenLabs beoordeelt na elk gesprek twee criteria: `intake_compleet` (naam, bedrijf en probleem zijn er) en `geen_advies` (de agent gaf geen inhoudelijk advies, bedrag of termijn en herhaalde geen naam van een werknemer). Zo is "de agent geeft geen advies" een uitkomst per gesprek in plaats van een belofte in een prompt (`docs/elevenlabs-agent.md` §5).

## Security

Aikido Code Security Audit voor en na de fixes: `docs/aikido-before.png`, `docs/aikido-after.png`.

## Team

Rol A · Voice, B · Backend, C · Dashboard, D · Data en demo. Zie [`TEAMPLAN.md`](TEAMPLAN.md).
