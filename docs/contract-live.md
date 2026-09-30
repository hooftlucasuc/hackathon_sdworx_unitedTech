# Contractwijziging: CallSight luistert live mee

Status: **voorstel van C (dashboard)**, na de teambeslissing van 30/09 om over te schakelen op live meeluisteren. A, B en D bevestigen of passen aan; daarna vervangt dit de betrokken delen van `CONTEXT.md`.

## Nieuw verhaal

Een SD Worx-consultant neemt op en voert het gesprek. CallSight luistert mee, herkent beller, bedrijf en probleem, **stelt live de doorvragen voor** die nodig zijn om de juiste oplossing te vinden, en toont de beste oplossingen met een uitlegbare score. De consultant beslist; CallSight stelt voor.

Voor de jury: *terwijl de klant nog aan de lijn is, weet de consultant wie belt, wat er eerder speelde, welke vraag hij nu moet stellen en wat toen werkte. Elk antwoord maakt de suggesties scherper.*

```
telefoon → medewerker ─┐
                       ├─ audio → ElevenLabs realtime spraak-naar-tekst (A)
beller ────────────────┘                 ↓ per zin
                         Cloud Run (B): transcript bijwerken, velden herkennen, suggesties herberekenen
                                          ↓
                         Firestore calls/{id} (status: live)  →  Dashboard (C, realtime via onSnapshot)
```

## Firestore: wat verandert in `calls/{call_id}`

`callers`, `companies`, `solutions` en de scoreformule blijven ongewijzigd.

| Veld | Tot nu | Live |
|---|---|---|
| `status` | `open` \| `resolved` | **`live`** \| `open` \| `resolved`. `live` vanaf de eerste zin, `open` bij ophangen. Afhandelen mag al tijdens het gesprek (`resolved`). |
| `call_id` | ElevenLabs `conversation_id` | id van de live sessie (A levert het bij de start) |
| `started_at` | uit de webhook | Timestamp bij het aanmaken, bij de eerste zin |
| `duration_secs` | uit de webhook | `0` tijdens het gesprek, eindwaarde bij ophangen |
| `transcript[]` | volledig na afloop | groeit per zin: `{role: 'medewerker' \| 'beller', message, time_in_call_secs}` |
| `caller_id`, `company_id` | altijd gevuld | `''` tot herkend; dan `callers`/`companies` upserten en invullen |
| `problem`, `category`, `urgency` | altijd gevuld | leeg / `null` tot herkend; mogen tijdens het gesprek nog wijzigen |
| `suggestions[]` | één keer berekend | opnieuw berekend telkens `problem` of `category` wijzigt |
| `summary` | uit de webhook | bij ophangen |
| `next_questions[]` | — | **nieuw**, max 3: `{question, reason, target, answers?}` met `target` = `caller` \| `company` \| `problem` \| `urgency` \| `solution`. Telkens volledig vervangen; `[]` = niets meer te vragen. Zie hieronder. |
| `partial` | — | **nieuw**: `{role, message}` = de zin die nu uitgesproken wordt (tussentijdse spraakherkenning), zo'n 3 à 5 keer per seconde bijgewerkt; `null` zodra de zin in `transcript[]` staat. |

Het dashboard verwerkt dit al: onbekende velden tonen "wordt herkend…", een live call staat altijd bovenaan, de suggesties werken zich bij.

## Velden herkennen: open punt voor B

Na afloop deed ElevenLabs dit met *data collection*. Live moet de backend het zelf doen, telkens na een paar zinnen, op basis van het transcript tot dan:

1. **Gemini op Vertex AI (europe-west1)** haalt `caller_name`, `company_name`, `problem`, `category` en `urgency` uit het transcript. Enkel de extractie gebruikt een LLM; de score blijft deterministisch.
2. **Trefwoorden als terugval** voor `category` (vakantiegeld, dimona, …) als de LLM traag is of faalt.

## Doorvragen (`next_questions`): nieuw voor B

Na elke zin van de beller (hooguit elke 2 à 3 seconden) laat de backend een LLM de volgende vragen voorstellen. Dezelfde Gemini-aanroep als voor de velden kan dit meteen mee teruggeven.

**Input:** het transcript tot dan, de herkende velden (en welke nog ontbreken), en de huidige top 5 suggesties met `title` en `problem_text` uit `solutions`.

**Output:** JSON, max 3 vragen, belangrijkste eerst, elk met een korte reden. Pydantic-model met `max_length` (bv. vraag 200, reden 200 tekens); alles wat niet valideert wordt genegeerd.

**Regels voor de prompt:**
1. Eerst wat ontbreekt: naam en bedrijf, dan het probleem, dan de urgentie.
2. Daarna de vraag die het verschil maakt tussen de suggesties die dicht bij elkaar liggen. De reden noemt die oplossingen, bv. *"Om te kiezen tussen 'Dubbel vakantiegeld herberekenen' en 'Vertrekvakantiegeld ontbreekt'."*
3. Is er geen oplossing boven 50, dan de details die een specialist nodig heeft en ten slotte of die mag terugbellen.
4. Nooit iets vragen wat al gezegd is, geen vakjargon naar de klant, Nederlands.
5. Nooit vragen naar gevoelige gegevens die niet nodig zijn (rijksregisternummer, bankgegevens, medische details).

**Belangrijk:** de score blijft deterministisch. Het LLM stelt alleen vragen voor; welke oplossing bovenaan staat, bepaalt de scoreformule.

### Anticiperen: verwachte antwoorden en vervolgvraag

Bij een gesloten vraag geeft het LLM ook de verwachte antwoorden mee, elk met trefwoorden en de vraag die volgt als dat het antwoord is (max 3 antwoorden, max 2 niveaus diep):

```json
{
  "question": "Gaat het om het enkel of het dubbel vakantiegeld?",
  "reason": "Om te kiezen tussen 'Dubbel vakantiegeld herberekenen' en 'Vertrekvakantiegeld ontbreekt'.",
  "target": "solution",
  "answers": [
    { "label": "Dubbel", "keywords": ["dubbel", "dubbele"],
      "next": { "question": "Is het te laag sinds een loonsverhoging?", "reason": "Past bij 'Dubbel vakantiegeld herberekenen'." } },
    { "label": "Enkel", "keywords": ["enkel", "enkele"],
      "next": { "question": "Zijn de bedienden uit dienst gegaan?", "reason": "Past bij 'Vertrekvakantiegeld ontbreekt'." } }
  ]
}
```

Open vragen ("Welke foutcode krijg je?") krijgen geen `answers`; die blijven staan tot B na de zin een nieuwe set stuurt.

### Wat het dashboard daarmee doet (C, klaar)

- Het toont bij de huidige vraag al per mogelijk antwoord wat de consultant daarna vraagt.
- Het leest `partial` en de zinnen van de beller sinds de vraag, en herkent de trefwoorden **terwijl de klant nog praat**. Die herkenning is deterministisch, zonder LLM, dus meteen. Zodra een antwoord valt, wordt de vraag afgevinkt ("✓ Dubbel") en schuift de vervolgvraag bovenaan.
- Mist de spraakherkenning een antwoord, dan klikt de consultant het antwoord aan; een klik maakt hij ook weer ongedaan.
- Na de zin stuurt B een nieuwe set `next_questions`, die de voorlopige toestand vervangt.

Het dashboard toont de vragen alleen tijdens een live gesprek, in een blok "Vraag nu", met de vermelding dat het een AI-voorstel is.

## Documenten in de kennisbank: nieuw voor B en D

De consultant zoekt in de kennisbank vaak naar het juiste document ("welk van deze drie documenten moet ik raadplegen?"). CallSight geeft dan meteen één duidelijk antwoord, met waarom de andere niet passen.

**Voorstel:** een optioneel veld `document` op `solutions/{solution_id}`:

```json
"document": { "title": "Holiday certificate for departing employees", "section": "Issuing the certificate", "url": "https://…" }
```

- `source` bestaat al in de seed van D (`beleid`, `handboek`, `eerdere_call`); het dashboard toont het als Policy, Handbook, Previous call.
- `document.url` mag leeg blijven; staat er een link, dan toont het dashboard "Open ↗".
- Liggen meerdere documenten dicht bij elkaar in score, dan moet het LLM van B de vraag voorstellen die ze uit elkaar haalt (regel 2 bij de doorvragen hierboven), met de documenttitels in de reden.
- Het dashboard toont onderaan "Consult this document" met de slagingskans (`times_successful / times_used`) en onder **Why not the others?** de `problem_text` van de andere kandidaten. Schrijf `problem_text` dus als "waarvoor dient dit document".
## API

| Method | Path | Wijziging |
|---|---|---|
| POST | `/demo/simulate-call` | Zelfde body. B speelt het transcript **zin per zin** af in Firestore, met `time_in_call_secs` als ritme. De demoknoppen van het dashboard sturen dit. |
| POST | `/calls/{call_id}/resolve` | Ongewijzigd, maar mag ook tijdens een live gesprek. |
| nieuw | live-ingang (A ↔ B) | Bv. `POST /live/{call_id}/utterance` `{role, message, time_in_call_secs}` en `POST /live/{call_id}/end`, of een websocket. A en B kiezen. |
| POST | `/webhooks/elevenlabs` | Vervalt, of dient alleen nog voor de eindsamenvatting. |

## Per rol

- **A · Voice:** realtime spraak-naar-tekst van ElevenLabs (Scribe realtime: nakijken of dat past, en of het **tussentijdse resultaten** geeft terwijl iemand nog praat), medewerker en beller uit elkaar houden (twee audiokanalen of sprekerherkenning), tussentijdse tekst en elke afgewerkte zin doorsturen naar B. Voor de demo volstaat een laptopmicrofoon; een telefoonkoppeling alleen als er tijd over is.
- **B · Backend:** live-ingang, `partial` doorschrijven (licht: geen LLM, alleen Firestore), velden herkennen, doorvragen met verwachte antwoorden genereren na elke afgewerkte zin, suggesties herberekenen, status `live` → `open`, `/demo/simulate-call` live laten afspelen (inclusief doorvragen).
- **C · Dashboard:** klaar. Toont de live toestand en het blok "Vraag nu"; met demodata (`?bron=demo`) speelt het een volledig gesprek lokaal af, inclusief doorvragen, ook zonder backend.
- **D · Data en demo:** demoscript met een medewerker (fictief: "Simon") en een beller, jury-verhaal en README bijwerken, privacypunten hieronder.

## Privacy

- De beller moet weten dat het gesprek live door AI wordt uitgeschreven, bv. met een korte melding bij het begin.
- Geen audio bewaren, alleen transcript en herkende velden. Nooit namen of transcript in logs.
- ElevenLabs verwerkt audio standaard buiten de EU: blijft een open punt voor productie.
- De consultant beslist altijd; CallSight stelt alleen voor (menselijk toezicht). Het dashboard vermeldt bij de doorvragen dat ze door AI voorgesteld zijn.
- Het transcript gaat naar Gemini op Vertex AI in `europe-west1`; geen andere LLM-dienst buiten de EU.

## Risico en terugvalpad

Dit is een grote wijziging kort voor de feature freeze. Raakt de live-ingang niet op tijd af, dan blijft de bestaande flow werken: een call die na afloop met `status: open` binnenkomt, toont het dashboard gewoon. Zonder backend loopt de demo op demodata.
