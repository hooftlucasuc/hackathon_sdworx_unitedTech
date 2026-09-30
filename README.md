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

Elke afgehandelde call ("werkte" / "werkte niet") past de succesratio aan: de kennisbank leert van wat in de praktijk werkt.

## Architectuur

```
telefoon / browser ─► ElevenLabs-agent ─► post-call webhook (HMAC) ─► Cloud Run (FastAPI) ─► Firestore (europe-west1)
                                                                          │ Vertex AI embeddings          │
                                                                          ▼ + vector search + score       ▼
                                                                                          Dashboard (React, realtime, login)
```

Score per oplossing: `100 × (0,60 × similarity + 0,25 × succesratio + 0,15 × recency)`. Deterministisch, geen LLM in de score. Details in [`TEAMPLAN.md`](TEAMPLAN.md) §1.5.

## Draaien

Vereisten: `gcloud`, `firebase` CLI, Python 3.11+, Node 20+, een ElevenLabs-account.

```bash
# 1. Google Cloud en Firebase (eenmalig)
gcloud auth login && gcloud auth application-default login
GCP_PROJECT=<project-id> ./infra/gcp_setup.sh
cp .env.example .env            # vul GCP_PROJECT en de ElevenLabs-waarden in

# 2. Fictieve dataset
python3 -m venv .venv && source .venv/bin/activate
pip install google-cloud-firestore google-cloud-aiplatform pydantic-settings
python scripts/seed.py --reset

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

- **Fictieve data.** Alle personen, bedrijven en experten in `data/seed/` zijn verzonnen; gelijkenis met bestaande personen of bedrijven is toevallig. Eén uitzondering: Lindsey Tafels (United Consulting) speelt de beller in de demo, met haar toestemming; haar cases in de seed zijn verzonnen. De kennisbank is een illustratie en geen juridisch advies.
- **Wat we bewaren:** transcript en de geëxtraheerde velden (naam, bedrijf, probleem, categorie, urgentie). **Geen audio.** Namen en transcripten komen nooit in logregels.
- **Waar:** Firestore, Vertex AI en Cloud Run draaien in `europe-west1`.
- **Toegang:** het dashboard leest alleen na login (Firestore security rules); schrijven kan uitsluitend de backend. De webhook weigert verzoeken zonder geldige HMAC-signature.
- **Open punten voor productie:**
  - ElevenLabs verwerkt audio standaard buiten de EU. Productie vereist EU-dataresidency of een gelijkwaardige garantie, een verwerkersovereenkomst en uitgeschakelde audio-opslag bij ElevenLabs.
  - Bewaartermijn per veld (bijvoorbeeld transcript 90 dagen, geëxtraheerde velden zolang het klantdossier loopt) en een verwijderprocedure op verzoek.
  - Rechtsgrond: uitvoering van de dienstverleningsovereenkomst met de werkgever; de beller wordt aan het begin van het gesprek geïnformeerd.

## EU AI Act

- **Transparantie (art. 50):** de agent zegt in de eerste zin dat de beller met een AI-assistent praat. Deze verplichting geldt sinds 2 augustus 2026.
- **Risico:** het systeem vat een vraag samen en stelt oplossingen voor aan een medewerker. Het neemt geen beslissingen over personen, beoordeelt geen werknemers en valt daarmee niet onder de hoog-risicocategorieën van bijlage III.
- **Mens in de lus:** een medewerker kiest de oplossing en belt terug. De score is uitlegbaar (drie deelwaarden) en het systeem escaleert zelf wanneer het geen sterke match heeft.

## Security

Aikido Code Security Audit voor en na de fixes: `docs/aikido-before.png`, `docs/aikido-after.png`.

## Team

Rol A · Voice, B · Backend, C · Dashboard, D · Data en demo. Zie [`TEAMPLAN.md`](TEAMPLAN.md).
