# Videoscript CallSight (doel 2:50, maximum 3:00)

De jury scoort op **originaliteit, techniek en fit met de case (elk 30%) en security (10%)**. Elke scène hieronder dient minstens één van die vier; dat staat in de laatste kolom.

Scenario's, bellerteksten en verwachte schermen staan in [`demo-script.md`](demo-script.md). Dit script legt vast wat we filmen, in welke volgorde, en wat de voice-over (VO) zegt.

## Overzicht

| Tijd | Scène | Beeld | Jury |
|---|---|---|---|
| 0:00–0:15 | 1. Het twijfelmoment | Drie documenten naast elkaar | fit |
| 0:15–0:25 | 2. Wat CallSight doet | Titelkaart en de flow | originaliteit |
| 0:25–1:30 | 3. Lindsey belt (scenario a) | Gesprek en dashboard in split-screen | techniek, fit |
| 1:30–1:50 | 4. Nieuwe beller, bekend bedrijf (b) | Dashboard | techniek |
| 1:50–2:20 | 5. Geen antwoord, wel een expert (c) | Dashboard | fit, originaliteit |
| 2:20–2:45 | 6. Onder de motorkap | Architectuur, Aikido, regio | techniek, security |
| 2:45–2:55 | 7. Slot | Titelkaart | |

Leeswerk voor de VO: ongeveer 280 woorden. Dat past in 2 minuten spreektijd; de rest is gesprek en beeld.

---

## Scène 1 · Het twijfelmoment (0:00–0:15)

**Beeld:** drie antwoorden naast elkaar op het scherm, als kaartjes: "Handboek 2023, geen eigenaar" · "Beleid, nagekeken 40 dagen geleden" · "Nederland". Langzaam inzoomen.

**VO:**
> Een klant belt SD Worx met een vraag over vakantiegeld. De medewerker vindt drie antwoorden: één uit een oud handboek zonder eigenaar, één recent nagekeken, en één dat voor Nederland geldt. Welk antwoord kan hij vertrouwen?

## Scène 2 · Wat CallSight doet (0:15–0:25)

**Beeld:** titelkaart "CallSight", daaronder de flow in één regel: *gesprek → AI-assistent → kennisbank met vertrouwenssignalen → medewerker*.

**VO:**
> CallSight luistert mee aan de voordeur. Nog voor iemand terugbelt, weet de medewerker wie belde, wat er eerder speelde, en welk antwoord hij kan vertrouwen, en waarom.

## Scène 3 · Lindsey belt (0:25–1:30)

**Beeld:** links het ElevenLabs-gesprek (golfvorm of browservenster), rechts het dashboard op `/live`. Ondertitels van het gesprek onderaan.

**Gesprek (ingekort in de montage tot ±30 s):**
- Agent, eerste zin (**laten staan**, is de AI Act-transparantie): *"Goeiedag, u spreekt met de digitale assistent van SD Worx. Ik ben een AI…"*
- Lindsey (A): naam, bedrijf, vraag over vertrekvakantiegeld, "vrij dringend". Tekst in `demo-script.md`.
- Agent vat samen en sluit af.

**Beeld na ophangen:** het dashboard springt naar de nieuwe call. Wacht niet in stilte: knip naar het moment dat de call verschijnt, en toon de gemeten tijd in een klein label ("verschijnt na X s").

**VO (terwijl het dashboard zich vult):**
> Lindsey Tafels van United Consulting, Comp & Ben. Het systeem herkent haar: dit is haar derde vraag over vakantiegeld, en ze heeft nog drie vragen openstaan. Die kan de medewerker in hetzelfde gesprek meenemen.

**Beeld:** inzoomen op de top-oplossing, uitleg openklappen (drie balkjes, eigenaar, reviewdatum).

**VO:**
> Bovenaan: het beleid over vertrekvakantiegeld. Score 89. Je ziet waarom: het past bij de vraag, het werkte in acht op de tien gesprekken, en An Wouters van Payroll België heeft het veertig dagen geleden nog nagekeken.

**Beeld:** scrollen naar de oude handboekversie met conflictwaarschuwing, daarna naar de Nederlandse oplossing met het label "geldt voor NL".

**VO:**
> En even belangrijk: welk antwoord je níet moet gebruiken. Een oude handboekversie zonder eigenaar, die de huidige regel tegenspreekt. En een antwoord dat wel lijkt te passen, maar voor Nederland geldt.

**Beeld:** klik "Gebruikt, werkte". De teller van de oplossing stijgt.

**VO:**
> Wat werkte, telt mee. Zo wordt de kennisbank bij elk gesprek betrouwbaarder.

## Scène 4 · Nieuwe beller, bekend bedrijf (1:30–1:50)

**Beeld:** gesprek versneld (2×) met ondertitels, dan het dashboard: lege beller-historie, volle bedrijfshistorie.

**VO:**
> Tom is nieuw bij Bakkerij Verhulst. Het systeem kent hem niet, maar het bedrijf wel: zijn collega stelde dezelfde vraag over maaltijdcheques al eerder, en dat antwoord komt meteen terug.

## Scène 5 · Geen antwoord, wel een expert (1:50–2:20)

**Beeld:** gesprek versneld, dan het dashboard met lage scores en de melding "geen sterke match, escaleer".

**VO:**
> Geert vraagt naar een arbeider die drie maanden vanuit Spanje wil werken. Dat staat nergens in de kennisbank. CallSight doet niet alsof het het weet.

**Beeld:** inzoomen op de doorverwijzing (Karim El Idrissi, sociaal-juridisch) en op de open call over de werf in Frankrijk in de bedrijfshistorie.

**VO:**
> Het toont wie gelijkaardige vragen behandelt, en dat dit bedrijf vorige maand al een vraag over buitenlands werk had die nog openstaat. Dat is een kennislacune die zichtbaar wordt, in plaats van een verzonnen antwoord.

## Scène 6 · Onder de motorkap (2:20–2:45)

**Beeld:** architectuurdiagram uit de README (5 s), dan de Aikido-screenshots voor en na naast elkaar (5 s), dan een shot van de Firestore-regio `europe-west1` (3 s).

**VO:**
> Onder de motorkap: ElevenLabs voor het gesprek, Google Cloud voor de rest. De score is deterministisch en uitlegbaar, zonder taalmodel. Alles staat in Europa, er wordt geen audio bewaard, en de assistent zegt vanaf de eerste zin dat hij een AI is. Aikido vond X problemen bij de start; na de fixes blijven er Y over.

(Vul X en Y in na de tweede scan.)

## Scène 7 · Slot (2:45–2:55)

**Beeld:** titelkaart "CallSight: find it, understand it, trust it", met de GitHub-URL.

**VO:**
> CallSight. Niet alleen een antwoord, maar de reden om het te vertrouwen.

---

## Opname en montage

- **Neem op in delen**, niet in één take: elke scène apart, zodat een mislukt gesprek niet alles kost. Tussen de takes: `python scripts/seed.py --reset --yes`.
- **Back-up:** neem één volledige geslaagde run op zodra de integratietest lukt, ook als die nog niet mooi is.
- **Scherm:** browser op 100% zoom, bladwijzerbalk verborgen, geen andere tabs, geen `.env` of terminal met secrets in beeld.
- **Gesprekken inkorten:** laat de eerste zin van de agent (AI-melding) en de vraag van de beller staan, knip de rest of versnel.
- **Ondertitels** bij alle gesprekken; de jury kijkt mogelijk zonder geluid.
- **Taal:** gesprekken in het Nederlands. VO in het Nederlands, met Engelse ondertitels als de jury niet volledig Nederlandstalig is (navragen).
- **Hosting:** YouTube (niet vermeld) of Drive met "iedereen met de link". Test de link in een incognitovenster.

## Nog in te vullen

- [ ] Gemeten tijd tussen ophangen en verschijnen op het dashboard (scène 3)
- [ ] Werkelijke topscore van scenario a (nu 89 in het script, uit de kalibratie in `demo-script.md`)
- [ ] Aantal Aikido-bevindingen voor en na (scène 6)
- [ ] Eerste zin van de agent zoals A die heeft ingesteld (scène 3)
- [ ] Wie spreekt de VO in, wie monteert
