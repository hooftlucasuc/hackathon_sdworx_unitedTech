# Demo-script CallSight

Drie gesprekken voor de video (< 3 min in totaal). In scenario a belt Lindsey Tafels (Comp & Ben, United Consulting) met een gegenereerde stem; A speelt de bellers in b en c, iemand anders bedient het dashboard.
Alle personen zijn fictief, ook Lindsey. United Consulting is het enige bestaande bedrijf; de cases ervan zijn verzonnen. Alles staat in `data/seed/`.

## Voorbereiding (voor elke take)

1. `python scripts/seed.py --reset --yes` (zet historie en tellers terug naar de beginstand; wist ook alle testcalls, dus niet tijdens een test van een teamgenoot).
2. Dashboard open op `/live`, browser op 100% zoom, geen andere tabbladen zichtbaar.
3. ElevenLabs-testgesprek klaar in een tweede venster. Lindsey (scenario a) is een gegenereerde stem, b en c spreekt A zelf in. Naam en bedrijf moeten **exact** zo in het transcript komen als hieronder: de herkenning van de beller hangt ervan af. Controleer dat na de eerste proefcall in het transcript op het ElevenLabs-dashboard.
4. Plan B: lukt een gesprek niet, gebruik de knop "Simuleer gesprek" (payloads in `samples/`) en zeg dat eerlijk in de voice-over.

## Scenario a: terugkerende beller (±90 s)

**Wat de jury moet zien:** de beller wordt herkend, de historie en de openstaande cases staan er al, en de topoplossing toont *waarom* ze betrouwbaar is.

Beller: Lindsey, met een gegenereerde stem. Elke beurt is een apart fragment (`python3 scripts/voiceover.py --caller`), dat de bediener afspeelt zodra de agent zwijgt. De beurten volgen het verloop van de agent uit `docs/elevenlabs-agent.md` §3: eerst het probleem (naam en bedrijf geeft Lindsey meteen mee, dus die vraag slaat de agent over), dan een samenvatting, dan de urgentie, dan de afsluiting. Wijkt de agent af, kies dan het reservefragment dat past.

> **L1 · na de begroeting ("Waarmee kan ik u helpen?"):** Goeiemiddag, met Lindsey Tafels van United Consulting, ik ben verantwoordelijk voor Comp & Ben. Ik bel over het vakantiegeld van een consultant die vorige maand uit dienst is gegaan. Hij krijgt veel minder vertrekvakantiegeld dan hij verwachtte, en hij denkt dat het vakantiegeld van vorig jaar er niet in zit.
> **L2 · na "Als ik het goed begrijp: … Klopt dat?":** Ja, dat klopt.
> **L3 · na "Moet dit vandaag opgelost zijn, deze week, of kan het wachten?":** Liefst vandaag nog. Hij heeft al twee keer gebeld.
> **L4 · bij de afsluiting:** Perfect, dank u wel. Tot horens.

Reserve, alleen als de agent iets anders doet:

> **R1 · na "Met wie spreek ik, en voor welk bedrijf belt u?":** Met Lindsey Tafels, van United Consulting.
> **R2 · als de agent de naam verkeerd herhaalt:** Nee, Lindsey Tafels. Tafels, zoals de meubels.
> **R3 · als de samenvatting niet klopt:** Niet helemaal. Het vakantiegeld van vorig jaar ontbreekt in zijn vertrekvakantiegeld.
> **R4 · als de agent iets onverwachts vraagt:** Sorry, kan u dat nog eens herhalen?

Afspelen: open `media/vo/<engine>/lindsey.html` (knoppen per fragment) op een **tweede toestel** naast de micro van de laptop waarop het gesprek loopt. Speel je af op dezelfde laptop, dan kan de echo-onderdrukking van de browser de stem wegfilteren.

Verwacht op het dashboard:
- Beller-historie: 3 afgehandelde calls van Lindsey, waarvan 2 over vakantiegeld (60 en 150 dagen geleden), en **3 openstaande cases**: mobiliteitsbudget (14 dagen), cafetariaplan (6 dagen), maaltijdcheques bij de klant (2 dagen). Zeg in de voice-over: *"De medewerker ziet meteen dat Lindsey nog drie vragen open heeft staan, en kan die in hetzelfde gesprek meenemen."*
- Bedrijf United Consulting: 6 calls, 3 open issues.
- Top-oplossing: **vg-01 Vertrekvakantiegeld van een bediende**, score ±83 (gemeten, zie kalibratie). Uitleg: hoge similarity, ±80% succes, recent gebruikt, eigenaar An Wouters (Payroll BE), nagekeken 40 dagen geleden.
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
| a | boven 80 | 83 (vg-01; 2e vg-02 77) | 0,79 | ✅ |
| b | boven 80 | 83 (mc-01; 2e ov-05 76) | 0,87 | ✅ |
| c | onder 80, escaleert | 63 (geen passende oplossing) | 0,46 | ✅ |

De gemeten waarden komen uit `python scripts/seed.py --probe`: dat scoort de drie scenario's tegen de kennisbank zonder iets te schrijven.
Gemeten op 30/09 met het lokale model van Cloud Run (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dims), in het geheugen met de volledige seed. Acht herformuleerde vragen die in de kennisbank zitten, scoorden 83 tot 89 (juiste oplossing telkens bovenaan); acht vragen die er niet in zitten, 63 tot 77. **Drempel: 80.** Met de standaardwaarde 60 escaleert niets, ook scenario c niet. De marge is klein (3 punten aan beide kanten): controleer bij de integratietest de echte scores, want de agent formuleert het probleem net anders dan hier. Zakt a of b onder 80, verlaag dan naar 78.

De backend escaleert als de beste score onder `ESCALATION_THRESHOLD` ligt (via de trigger-substitutie `_ESCALATION_THRESHOLD`, dus **80** zetten). Haalt c die drempel niet, verhoog hem dan tot net boven de topscore van c en onder die van b, en meld het aan B en C.
