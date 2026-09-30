# CallSight — dashboard (rol C)

Een SD Worx-medewerker voert het gesprek; CallSight luistert mee en toont tijdens het gesprek wie belt, wat er eerder speelde en welke oplossingen toen werkten. Contractwijziging voor live meeluisteren: [`../docs/contract-live.md`](../docs/contract-live.md).

Vite + React + TypeScript. Leest realtime uit Firestore (`onSnapshot`, alleen lezen) en schrijft via de API van B.

## Starten

```bash
npm install
cp .env.example .env.local
npm run dev
```

Opent op http://localhost:5173 (= `FRONTEND_ORIGIN` in de backend-CORS).

## Twee modi

| `VITE_DATA_SOURCE` | Wat |
|---|---|
| `mock` (standaard) | Dummydata in de browser volgens het contract, inclusief de scoreformule. Demo-knoppen voegen een call toe. Geen backend nodig. |
| `firestore` | Realtime uit Firestore (`calls`, `callers`, `companies`, `solutions`). "Werkte / Werkte niet" → `POST /calls/{id}/resolve`, demo-knoppen → `POST /demo/simulate-call`. |

Met `VITE_DEMO_MODE=true` staan bovenaan drie knoppen voor de demo-scenario's (terugkerende beller, nieuwe collega bij een bekend bedrijf, onbekend probleem). Elke knop speelt een gesprek van ongeveer 25 seconden live af: het transcript loopt binnen, beller en probleem worden herkend en de suggesties worden scherper. Met demodata gebeurt dat in de browser; live stuurt de knop `POST /demo/simulate-call` en speelt B het af. Voor een demo met een echt gesprek zet je de knoppen op `false`.

## Plan B op de demodag

Valt Firestore of de backend weg, dan hoef je niets te herstarten:

- Krijgt het dashboard na 8 seconden geen gegevens of lukt het verbinden niet, dan verschijnt een melding met de knop **Overschakelen naar demodata**.
- Of zet zelf `?bron=demo` achter de URL: http://localhost:5173/?bron=demo. Met **terug naar live** naast "● Demodata" of `?bron=live` keer je terug.

Demodata leven alleen in de browser: herladen zet ze terug op de beginstand.

Faalt één onderdeel van het scherm (bv. door onverwachte data), dan toont alleen dat onderdeel een melding met **Opnieuw proberen**; de rest blijft werken.

## Wat het scherm toont

- **Links:** de 15 recentste calls; een lopend gesprek staat bovenaan met "● Live". Het scherm volgt automatisch de nieuwste call; klik je een oudere aan, dan brengt "Naar nieuwste" je terug.
- **Midden:** beller ("3e call" of "Nieuwe beller"), bedrijf, urgentie en probleem. Tijdens een gesprek lopen een timer en het transcript mee, en velden die nog niet herkend zijn tonen "wordt herkend…". Het blok **Vraag nu** toont tijdens het gesprek de doorvragen die CallSight voorstelt (`next_questions`), elk met de reden waarom de vraag helpt, en per mogelijk antwoord al de vervolgvraag. Terwijl de klant nog praat (`partial`) herkent het dashboard het antwoord (`src/answers.ts`), vinkt de vraag af en zet de vervolgvraag bovenaan; de consultant kan een antwoord ook aanklikken. Daaronder de top 5 oplossingen; de punten per deelwaarde (gelijkenis, succes, recent) tellen op tot de score. Is de beste score lager dan 50, dan staat er tijdens het gesprek "nog geen sterke match" en na afloop "escaleer naar een expert".
- **Rechts:** beller-historie en bedrijfshistorie (calls van collega's), telkens met de oplossing die toen gekozen werd.

## Wat het dashboard van de andere rollen verwacht

- **B:** `calls.started_at` als Firestore-Timestamp (daarop wordt gesorteerd). De score staat op 0–100, de `reasons` op 0–1. CORS staat open voor `http://localhost:5173`.
- **B/D:** Firestore-rules die lezen toestaan voor het dashboard. Omdat gespreksdata persoonsgegevens zijn, zet je die niet publiek open. Een voorstel: Anonymous Auth aanzetten in Firebase, `VITE_FIREBASE_ANON_AUTH=true`, en:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{db}/documents {
    match /{col}/{id} {
      allow read: if request.auth != null && col in ['calls', 'callers', 'companies', 'solutions'];
      allow write: if false;
    }
  }
}
```

## Structuur

```
src/
  types.ts            contract (collecties, score-gewichten, escalatiedrempel)
  data/firestore.ts   realtime lezen uit Firestore
  data/mock.ts        dummydata + scoreformule voor offline werken
  data/demoPayloads.ts  de 3 scenario's als ElevenLabs-webhookbody
  data/hooks.ts       React-hooks bovenop de gekozen databron
  api.ts              resolve + simulate-call
  components/         CallList, CallDetail, Suggestions, History
```
