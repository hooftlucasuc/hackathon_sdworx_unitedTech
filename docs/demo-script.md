# Demo-script CallSight

Drie gesprekken voor de video (< 3 min in totaal). In scenario a belt Lindsey Tafels (Comp & Ben, United Consulting); A speelt alle bellers, iemand anders bedient het dashboard.
Alle personen zijn fictief, ook Lindsey. United Consulting is het enige bestaande bedrijf; de cases ervan zijn verzonnen. Alles staat in `data/seed/`.

## Voorbereiding (voor elke take)

1. `cd callsight && python scripts/seed.py --reset` (zet historie en tellers terug naar de beginstand).
2. Dashboard open op `/live`, browser op 100% zoom, geen andere tabbladen zichtbaar.
3. ElevenLabs-testgesprek klaar in een tweede venster. Spreek rustig en noem naam en bedrijf **exact** zoals hieronder: de herkenning van de beller hangt ervan af.
4. Plan B: lukt een gesprek niet, gebruik de knop "Simuleer gesprek" (payloads in `samples/`) en zeg dat eerlijk in de voice-over.

## Scenario a: terugkerende beller (±90 s)

**Wat de jury moet zien:** de beller wordt herkend, de historie en de openstaande cases staan er al, en de topoplossing toont *waarom* ze betrouwbaar is.

Beller (Lindsey):
> Goeiemiddag, met Lindsey Tafels van United Consulting, ik ben verantwoordelijk voor Comp & Ben.
> Ik bel over het vakantiegeld van een consultant die vorige maand uit dienst is gegaan. Hij krijgt veel minder vertrekvakantiegeld dan hij verwachtte, en hij denkt dat het vakantiegeld van vorig jaar er niet in zit.
> Het is vrij dringend, hij heeft al twee keer gebeld.

Verwacht op het dashboard:
- Beller-historie: 3 afgehandelde calls van Lindsey, waarvan 2 over vakantiegeld (60 en 150 dagen geleden), en **3 openstaande cases**: mobiliteitsbudget (14 dagen), cafetariaplan (6 dagen), maaltijdcheques bij de klant (2 dagen). Zeg in de voice-over: *"De medewerker ziet meteen dat Lindsey nog drie vragen open heeft staan, en kan die in hetzelfde gesprek meenemen."*
- Bedrijf United Consulting: 6 calls, 3 open issues.
- Top-oplossing: **vg-01 Vertrekvakantiegeld van een bediende**, score boven 85. Uitleg: hoge similarity, ±80% succes, recent gebruikt, eigenaar An Wouters (Payroll BE), nagekeken 40 dagen geleden.
- Lager in de lijst: **vg-04**, de oude handboekversie zonder eigenaar, met een waarschuwing dat ze tegenstrijdig is met vg-01. Wijs daarop: *het systeem toont niet alleen een antwoord, maar ook welk antwoord je níet moet vertrouwen.*
- **vg-05** (Nederland) scoort qua tekst hoog, maar krijgt het label "geldt voor NL". Voor deze Belgische klant is dat niet van toepassing.

Afsluiten: klik "Gebruikt, werkte" bij vg-01; de teller stijgt live.

## Scenario b: nieuwe beller, bekend bedrijf (±40 s)

**Wat de jury moet zien:** het systeem kent de persoon niet, maar kent het bedrijf wel.

Beller (A):
> Dag, u spreekt met Tom Wuyts, ik ben de nieuwe HR-medewerker bij Bakkerij Verhulst.
> Ik wil weten hoeveel maaltijdcheques een verkoopster krijgt die maar drie dagen per week werkt.
> Het is niet dringend.

Verwacht op het dashboard:
- Beller-historie: leeg (eerste call).
- Bedrijfshistorie: 7 of meer calls van Sofie en Wim, waaronder dezelfde vraag van Wim 400 dagen geleden.
- Top-oplossing: **mc-01 Aantal maaltijdcheques voor deeltijdse werknemers**, hergebruikt.

## Scenario c: onbekend probleem (±40 s)

**Wat de jury moet zien:** het systeem doet niet alsof het het weet, en verwijst naar een expert.

Beller (A):
> Goeiemiddag, met Geert Claes van Bouwbedrijf Claes.
> Een van onze arbeiders gaat drie maanden telewerken vanuit Spanje. Moet ik daar iets voor regelen voor de sociale zekerheid?
> Redelijk dringend, hij vertrekt volgende maand.

Verwacht op het dashboard:
- Geen oplossing boven de drempel, melding **"geen sterke match, escaleer"**.
- Bedrijfshistorie: een open call van 40 dagen geleden over een werf in Frankrijk. Dezelfde kennislacune komt terug.
- Doorverwijzing: **Karim El Idrissi (sociaal-juridisch advies)**, afgeleid uit wie gelijkaardige vragen behandelt.

## Voice-over (kern, eigen woorden mogen)

- Opening: *"Een klant belt SD Worx. De medewerker vindt drie antwoorden: één recent, één zonder eigenaar, één voor een ander land. Welk antwoord kan hij vertrouwen?"*
- Na scenario a: *"CallSight toont niet alleen de beste match, maar ook waarom: wie het antwoord beheert, wanneer het werd nagekeken, hoe vaak het echt werkte, en voor welk land het geldt."*
- Na scenario c: *"Waar de kennis ophoudt, zegt het systeem dat, en wijst het de collega aan die het wel weet."*
- Slot: security (signature op de webhook, Firestore alleen lezen met login), alles in europe-west1, geen audio bewaard, elke afgehandelde call voedt de kennisbank.

## Kalibratie (in te vullen na de eerste echte run)

| Scenario | Topscore verwacht | Gemeten | Topsimilarity | OK? |
|---|---|---|---|---|
| a | > 85 | | | |
| b | > 75 | | | |
| c | onder de escalatiedrempel | | | |

Haalt c de drempel niet, pas de drempel aan op de **hoogste similarity** (niet op de totaalscore) en meld het aan B en C.
