# ElevenLabs-agent — CallSight intake

Rol A. Dit bestand is de bron van waarheid voor de agent: `scripts/elevenlabs_setup.py`
bouwt zijn request uit de config in §7, zodat de agent reproduceerbaar is en niemand
in het dashboard hoeft te klikken om te weten wat erin staat.

Veldnamen en toegestane waarden zijn gecontroleerd tegen de actuele docs, zie
[elevenlabs-payload-check.md](elevenlabs-payload-check.md).

Eén ding vooraf, omdat het de hele privacyredenering draagt: **de agent luistert niet
mee met een gesprek, hij voert het gesprek.** Er zit geen mens aan de andere kant die
opgenomen wordt. De beller praat met een machine, hoort dat in de eerste zin, en een
menselijke collega belt daarna terug. Dat is een wezenlijk andere situatie dan een AI
die meeluistert met een mens-mens-gesprek, en het is de makkelijkere van de twee.

## 1. Identiteit en modelkeuzes

| Instelling | Waarde | Waarom |
|---|---|---|
| Naam | `CallSight intake NL` | |
| Taal | `nl` | |
| TTS-model | `eleven_flash_v2_5` | het standaardmodel `eleven_flash_v2` is **Engels-only**; voor Nederlands moet je naar v2.5 of `eleven_multilingual_v2`. v2.5 is de snelste van de twee. |
| Stem | `5fPlr1QYE4Evf0da3knC` — Florian De'Booser, nl-BE | zie §1.1. Staat in `.env` als `ELEVENLABS_VOICE_ID`; leeg laten geeft de ElevenLabs-default `cjVigY5qzO86Huf0OWal`, een Engelse stem. |
| Gespreks-LLM | `gemini-2.5-flash` | latency telt in een telefoongesprek. `claude-haiku-4-5` is een gelijkwaardig alternatief; het staat in dezelfde enum. |
| Analyse-LLM | `gemini-2.5-flash` | doet de extractie ná het gesprek; hier telt latency niet, maar wel consistentie. |
| ASR | `scribe_realtime`, quality `high` | met `keywords` voorgeladen op payroll-jargon, zie §7. |
| Max duur | 180 s | default is 600. Drie minuten is ruim voor een intake, en het voorkomt dat een vergeten tabblad credits opbrandt. |
| Samenvattingstaal | `nl` | zonder deze instelling raadt ElevenLabs de taal van samenvatting, titel en rationales. |

### 1.1 Waarom deze stem

De Voice Library geeft op `language=nl` dertig conversationele stemmen, maar
negenentwintig daarvan zijn nl-NL. Onze bellers zijn Belgische werkgevers, en een
Noord-Nederlandse harde g op een SD Worx-lijn valt meteen op.

Er is precies één Vlaamse stem die op het gratis plan mag: **Florian De'Booser**,
`5fPlr1QYE4Evf0da3knC`, locale nl-BE, accent flemish, use case conversational. Die is
aan de workspace toegevoegd en staat in `.env`.

Van de nl-NL-stemmen kwam Maaike (`xoc65D3DrU0JxBTKaSgV`, Brabants accent met zachte g)
qua klank het dichtst in de buurt, maar die vereist een betaald plan — de API antwoordt
`paid_plan_required`. Gaat de workspace ooit naar een betaald plan, dan is dat het
alternatief om te proberen.

De agent bestaat en draait: `agent_2601m3svj41kfdjtyknae30gckya`. Een nieuwe run van
`scripts/elevenlabs_setup.py` werkt hem bij, want dat id staat in `.env`; hij maakt geen
tweede agent aan.

## 2. First message

```
Goeiedag, u spreekt met de automatische assistent van SD Worx. Ik neem uw vraag op
zodat een collega u kan terugbellen. Waarmee kan ik u helpen?
```

Dat de beller in de eerste zin hoort dat hij met een machine praat, is geen
beleefdheid maar een verplichting: de AI Act vraagt dat iemand weet dat hij met een
AI-systeem te maken heeft. Haal die zin er dus niet uit om de demo vlotter te laten
klinken.

## 3. System prompt

Dit is de letterlijke tekst die in `conversation_config.agent.prompt.prompt` gaat.

```text
# Rol
Je bent de telefonische intake-assistent van SD Worx. Je bent een AI en je doet
nooit alsof je een medewerker bent. Je spreekt Nederlands, beleefd en to the point,
en je spreekt de beller aan met u.

# Doel
Je neemt een inkomende oproep aan van een werkgever met een payrollvraag. Je hebt
één taak: vaststellen wie belt, van welk bedrijf, wat het probleem is en hoe
dringend het is. Een menselijke collega belt daarna terug met de oplossing.

# Wat je nooit doet
- Je geeft geen advies, geen berekening, geen inschatting en geen inhoudelijk
  antwoord, ook niet als de beller aandringt. Je zegt dan: "Daar kan ik u zelf niet
  mee verder helpen, maar ik zorg dat de juiste collega u terugbelt."
- Je herhaalt geen loonbedragen, rijksregisternummers, rekeningnummers of
  geboortedata die de beller noemt.
- Je herhaalt geen namen van werknemers, ex-werknemers of andere derden. Je spreekt
  over "een bediende", "een werknemer", "iemand die uit dienst ging".
- Je vraagt niet naar gegevens die je niet nodig hebt: geen rijksregisternummer,
  geen klantnummer, geen rekeningnummer.
- Je belooft geen termijn, geen bedrag en geen uitkomst.

# Verloop
Houd het gesprek onder de zes eigen beurten.
1. Begroet, zeg dat je de automatische assistent van SD Worx bent, vraag waarmee je
   kunt helpen.
2. Laat de beller het probleem uitleggen. Onderbreek niet. Stel hoogstens één
   verduidelijkende vraag, en alleen als je echt niet begrijpt waar het over gaat.
3. Vraag naam en bedrijf als de beller die niet uit zichzelf gegeven heeft, samen in
   één zin: "Met wie spreek ik, en voor welk bedrijf belt u?"
4. Vat het probleem samen in één zin en vraag of dat klopt. Begin met "Als ik het
   goed begrijp: ". Verbetert de beller je, neem dan zijn formulering over.
5. Vraag hoe dringend het is: "Moet dit vandaag opgelost zijn, deze week, of kan het
   wachten?"
6. Sluit af: bevestig dat een collega terugbelt, bedank, en beëindig het gesprek met
   de end_call-tool.

# Als iets ontbreekt
- Geeft de beller zijn naam of bedrijf niet, vraag het één keer opnieuw. Weigert hij,
  ga door zonder. Blijf niet aandringen.
- Is het probleem na twee pogingen nog onduidelijk, noteer wat je wel hebt en sluit af.
- Gaat de vraag niet over payroll, zeg dat je enkel payrollvragen aanneemt en sluit af.

# Toon
Korte zinnen. Geen jargon, geen opsommingen, geen "uiteraard" of "absoluut". Klink als
iemand die efficiënt een formulier invult, niet als een verkoper.
```

De begrenzing op zes beurten is promptwerk, geen instelling: ElevenLabs kent geen harde
beurtlimiet. De echte vangrail is `max_duration_seconds` in §7.

## 4. Data collection — de vijf velden

Dit is het belangrijkste deel van de config. De **beschrijving** is wat de extractie
stuurt; de veldnaam doet niets. Elke beschrijving zegt daarom drie dingen: wat je wél
wil, wat je níét wil, en wat er moet gebeuren als het ontbreekt.

| Veld | Type | Enum |
|---|---|---|
| `caller_name` | string | — |
| `company_name` | string | — |
| `problem` | string | — |
| `category` | string | `vakantiegeld` `loonberekening` `ziekte` `dimona` `maaltijdcheques` `bedrijfswagen` `ontslag` `overig` |
| `urgency` | string | `laag` `midden` `hoog` |

De enums staan als echte `enum` in de API, niet enkel als zin in de beschrijving — zie
§4 van de payload-check. B blijft desondanks valideren: een veld kan leeg terugkomen,
en `value` is optioneel in de payload.

**caller_name**
```
De volledige naam van de persoon die belt, zoals hij of zij die zelf opgeeft. Alleen
de beller zelf, niet de naam van een werknemer, ex-werknemer of collega die in het
gesprek ter sprake komt. Geef voornaam en achternaam in normale spelling, zonder
aanspreking: "Sofie Janssens", niet "mevrouw Janssens". Noemt de beller geen naam,
laat dit veld dan leeg.
```

**company_name**
```
De naam van het bedrijf of de organisatie waarvoor de beller belt, inclusief de
rechtsvorm als die genoemd wordt (BV, NV, VZW, CV). Nooit "SD Worx": dat is de partij
die opneemt, niet de klant. Noemt de beller enkel een handelsnaam of een afkorting,
neem dan letterlijk over wat hij zegt. Wordt er geen bedrijf genoemd, laat dit veld
dan leeg.
```

**problem**
```
Eén zin in het Nederlands die beschrijft welk concreet probleem of welke vraag de
beller heeft, geformuleerd in de derde persoon. Neem het onderwerp, de aanleiding en
de periode mee als die genoemd zijn. Voorbeeld: "Het vakantiegeld van een bediende die
in maart uit dienst ging klopt niet." Neem geen bedragen, rijksregisternummers,
rekeningnummers, geboortedata of namen van werknemers op: schrijf "een bediende" of
"een werknemer". Is er geen duidelijk probleem uitgesproken, laat dit veld dan leeg.
```

**category**
```
De categorie waarin het probleem van de beller valt. Kies er precies één.
"vakantiegeld": enkel of dubbel vakantiegeld, vertrekvakantiegeld, vakantieattest.
"loonberekening": fouten in bruto- of nettoloon, bedrijfsvoorheffing, RSZ, index,
barema. "ziekte": gewaarborgd loon, arbeidsongeschiktheid, ziekteattest, langdurig
zieken. "dimona": Dimona-aangiften, DmfA, in- en uitdienstmeldingen.
"maaltijdcheques": maaltijd-, eco- en cadeaucheques. "bedrijfswagen": bedrijfswagens,
tankkaarten, voordeel alle aard, mobiliteitsbudget. "ontslag": opzegtermijn,
verbrekingsvergoeding, C4, outplacement. Kies "overig" alleen wanneer geen enkele
andere categorie past.
```

**urgency**
```
Hoe dringend de beller het probleem vindt, op basis van wat hij zegt over de termijn.
"hoog": het moet vandaag of morgen opgelost zijn, er dreigt een wettelijke deadline of
een loonrun, of de beller zegt zelf dat het dringend is. "midden": het moet deze week
of voor de volgende loonrun. "laag": het kan wachten, of het is een vraag zonder
deadline. Zegt de beller niets over dringendheid, kies dan "midden".
```

## 5. Evaluation criteria

Twee eigen criteria. Ze staan los van het ingebouwde `call_successful`, dat ElevenLabs
zelf invult met `success`, `failure` of `unknown`.

**intake_compleet**
```
De intake is geslaagd wanneer de assistent aan het eind van het gesprek drie dingen
heeft: de naam van de beller, de naam van zijn bedrijf, en een concreet omschreven
probleem. Geef "success" wanneer alle drie aanwezig zijn, ook als de samenvatting kort
was. Geef "failure" wanneer een van de drie ontbreekt.
```

**geen_advies**
```
Controleer of de assistent zich aan zijn beperking gehouden heeft. Geef "failure"
wanneer de assistent inhoudelijk advies gaf, een bedrag of berekening noemde, een
termijn of uitkomst beloofde, of een loonbedrag, rijksregisternummer of de naam van een
werknemer herhaalde. Geef in alle andere gevallen "success".
```

Dat tweede criterium is er voor de jury én voor onszelf: het maakt van "de agent geeft
geen advies" een meetbare uitkomst per gesprek in plaats van een belofte in een prompt.

## 6. Post-call webhook

De webhook wordt **één keer op workspace-niveau** aangemaakt, niet per agent, en
daarna aangezet voor de agents: [elevenlabs.io/app/agents/settings](https://elevenlabs.io/app/agents/settings).

1. Maak de webhook aan met auth-type HMAC. ElevenLabs toont het secret **één keer** —
   zet het meteen in `.env` als `ELEVENLABS_WEBHOOK_SECRET` en geef het via een
   wachtwoordkluis door aan B. Niet in Teams, niet in de repo, niet in een screenshot.
2. Zet als URL het `POST /webhooks/elevenlabs`-endpoint van B.
3. Zet alleen `post_call_transcription` aan. Laat `post_call_audio` uit: wij bewaren
   geen audio, en die payload zou door dezelfde parser gaan.

**URL wisselen van ngrok naar Cloud Run.** Tot B's Cloud Run-service staat, wijst de
webhook naar een ngrok-tunnel. Bij het wisselen:

1. Pas de URL aan in de webhookinstellingen. Het secret blijft hetzelfde, dus B hoeft
   niets te herconfigureren.
2. Stuur meteen daarna `scripts/replay_webhook.py` naar de nieuwe URL. Dat is de
   controle dat de signature langs de nieuwe kant nog klopt.
3. Let op de auto-uitschakeling: tien mislukte pogingen op rij en ElevenLabs zet de
   webhook uit, met heraanzetten alleen via de settings-pagina. Een ngrok-tunnel die al
   een half uur dood is terwijl er getest wordt, komt daar snel aan. Wissel dus op het
   moment dat Cloud Run daadwerkelijk antwoordt, niet ervoor.

Een ngrok-URL verandert bij elke herstart. Verandert hij, dan verandert stap 1 mee.

## 7. Volledige config

Dit is de body voor `POST /v1/convai/agents/create`. `scripts/elevenlabs_setup.py`
leest dezelfde structuur en vult `prompt`, `voice_id` en de beschrijvingen in vanuit
dit bestand en uit `.env`.

```json
{
  "name": "CallSight intake NL",
  "tags": ["hackathon", "callsight"],
  "conversation_config": {
    "agent": {
      "language": "nl",
      "first_message": "Goeiedag, u spreekt met de automatische assistent van SD Worx. Ik neem uw vraag op zodat een collega u kan terugbellen. Waarmee kan ik u helpen?",
      "prompt": {
        "prompt": "<de tekst uit paragraaf 3>",
        "llm": "gemini-2.5-flash",
        "temperature": 0.2,
        "built_in_tools": {
          "end_call": {
            "name": "end_call",
            "type": "system",
            "params": {"system_tool_type": "end_call"}
          }
        }
      }
    },
    "tts": {
      "model_id": "eleven_flash_v2_5",
      "voice_id": "<ELEVENLABS_VOICE_ID>",
      "stability": 0.5,
      "speed": 1.0
    },
    "asr": {
      "provider": "scribe_realtime",
      "quality": "high",
      "keywords": [
        "vakantiegeld", "vertrekvakantiegeld", "Dimona", "DmfA", "maaltijdcheques",
        "ecocheques", "RSZ", "bedrijfsvoorheffing", "paritair comite", "C4",
        "opzegtermijn", "voordeel alle aard", "gewaarborgd loon", "loonrun"
      ]
    },
    "turn": {"turn_timeout": 7, "turn_eagerness": "normal"},
    "conversation": {"max_duration_seconds": 180}
  },
  "platform_settings": {
    "summary_language": "nl",
    "analysis_llm": "gemini-2.5-flash",
    "data_collection": {
      "caller_name":  {"type": "string", "description": "<paragraaf 4>"},
      "company_name": {"type": "string", "description": "<paragraaf 4>"},
      "problem":      {"type": "string", "description": "<paragraaf 4>"},
      "category":     {"type": "string", "description": "<paragraaf 4>",
                       "enum": ["vakantiegeld", "loonberekening", "ziekte", "dimona",
                                "maaltijdcheques", "bedrijfswagen", "ontslag", "overig"]},
      "urgency":      {"type": "string", "description": "<paragraaf 4>",
                       "enum": ["laag", "midden", "hoog"]}
    },
    "evaluation": {
      "criteria": [
        {"id": "intake_compleet", "name": "intake_compleet", "type": "prompt",
         "conversation_goal_prompt": "<paragraaf 5>"},
        {"id": "geen_advies", "name": "geen_advies", "type": "prompt",
         "conversation_goal_prompt": "<paragraaf 5>"}
      ]
    }
  }
}
```

De ASR-keywords zijn geen luxe: "Dimona", "DmfA" en "C4" komen er zonder boost
regelmatig verminkt uit, en dan mist de extractie de categorie.

## 8. Privacy

- Alleen fictieve bellers en fictieve bedrijven, ook in de testgesprekken waarvan we de
  payloads in `samples/` bewaren. Spreek in een testgesprek nooit een echte klantnaam
  in: die payload komt in de repo terecht.
- De agent vraagt geen rijksregisternummer, klantnummer of rekeningnummer. Dat staat in
  de prompt en wordt per gesprek gemeten door `geen_advies`.
- Bij elk data-collection-veld geeft ElevenLabs een `rationale` terug: een LLM-zin over
  waarom dat de waarde is. Bruikbaar als tooltip, maar het is een persoonsgegeven. Niet
  in logs.
- ElevenLabs verwerkt standaard buiten de EU. Zie §5 van de payload-check voor wat er
  precies nodig is om dat te veranderen, en wat ook dán nog buiten de EU blijft.

## 9. Test

Een browser-testgesprek van één minuut is geslaagd wanneer de payload alle vijf velden
gevuld heeft, `category` een waarde uit de enum is, `problem` geen bedrag of
persoonsnaam bevat, en beide evaluation criteria op `success` staan. Die payload gaat
als `samples/postcall_01.json` de repo in en wordt daarna de testinvoer van B en C via
`scripts/replay_webhook.py`.
