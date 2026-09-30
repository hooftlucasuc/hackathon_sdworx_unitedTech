# De luisteraar — meeluisteren in plaats van praten

Rol A. `CONTEXT.md` en `TEAMPLAN.md` beschrijven een agent die zelf het gesprek voert.
Dat is niet wat we bouwen: de AI **luistert mee** met een gesprek tussen een klant en een
medewerker, zegt niets, en duwt de vijf velden naar de tool terwijl de vraag nog gesteld
wordt. Dit document beschrijft wat daarvoor nodig is en wat ervan werkt.

```
microfoon beller ─► Scribe v2 Realtime (WebSocket) ─┐
                                                     ├─► segment_collector ─► backend ─► dashboard
microfoon medewerker ─► Scribe v2 Realtime ─────────┘        (extractie)
```

## Wat verandert aan het contract

Alleen **§1.2** sneuvelt: de post-call webhook met HMAC. §1.1 (de vijf velden), §1.3
(Firestore), §1.4 (de API) en §1.5 (de score) blijven exact zoals ze zijn. De collector
stuurt een payload in precies de vorm van §1.2, zodat B's parser ongewijzigd blijft.
Alleen `status` is nu `in_progress` in plaats van `done`, en dezelfde `conversation_id`
komt meerdere keren langs — elke keer met een langere transcript.

Dat betekent voor B: de upsert op `conversation_id` moet meerdere keren over hetzelfde
gesprek heen kunnen, en de tellers mogen niet elke keer ophogen. Dat stond al als punt
3.4 in [elevenlabs-payload-check.md](elevenlabs-payload-check.md), maar nu is het de
normale gang van zaken in plaats van een randgeval bij een retry.

## Diarisatie: realtime kan het niet

De WebSocket `/v1/speech-to-text/realtime` heeft geen `diarize`, geen `num_speakers` en
geen multichannel. Er zit wel een `speaker_id` in het antwoordschema, maar met de
toevoeging *"if available"* en zonder schakelaar.

De batch-API heeft het allemaal wél, inclusief `detect_speaker_roles`, dat letterlijk
`agent` en `customer` teruggeeft. Dat is exact onze use case — maar batch werkt pas ná
het gesprek, en dan is het te laat.

**Daarom scheiden we bij de bron: één WebSocket-sessie per spreker.** Beller en
medewerker krijgen elk hun eigen microfoon en dus hun eigen sessie. Dat is geen
noodgreep; het is betrouwbaarder dan een model dat stemmen uit elkaar moet houden op een
ruizige lijn, en het maakt `speaker` een feit in plaats van een gok.

## Audiobron: die komt niet van ElevenLabs

Alle telefonie-integraties van ElevenLabs — Twilio native, SIP trunking, Genesys — horen
bij de Agents-laag en koppelen een *pratende* agent aan een lijn. Er is geen pad dat een
gesprek tussen twee mensen aftapt. De audio moet dus van onze kant komen:

- **Client-side:** browsermicrofoon met een single-use token
  (`tokens.singleUse.create("realtime_scribe")`, vervalt na 15 minuten). Zo komt de
  API-key nooit in de browser.
- **Server-side:** onze eigen backend duwt de audio erin met de API-key. Kan ook van een
  URL streamen, maar dan is `ffmpeg` nodig.

Voor de demo: twee laptops of twee browservensters, elk met een eigen microfoon en een
eigen sessie. Voor productie moet het telefonieplatform van SD Worx ons de mediastroom
geven — Twilio Media Streams, een SIP-recorder of een softphone. **Dat is het grootste
open punt van dit ontwerp**, en het is een gesprek met hun telco, niet met ElevenLabs.

## Vallen die tijd kostten

- **`keyterms` wordt herhaald als query-parameter**, niet komma-gescheiden en niet als
  JSON-array: `?keyterms=Dimona&keyterms=DmfA`. Stuur je één lange string, dan is dat
  één keyterm van meer dan 20 tekens en sluit de server de WebSocket met een kaal
  `1008 invalid_request` zonder enige uitleg. Realtime staat 50 termen toe van elk
  hoogstens 20 tekens; batch mag er 1000 van elk 50.
- **`commit_strategy` moet `vad` zijn, kleine letters.** `VAD` wordt geweigerd, opnieuw
  met een kaal `invalid_request`.
- Het `session_started`-event echoot de hele config terug. Dat is de snelste manier om
  te zien wat de server van je parameters gemaakt heeft: `language_code=nld` komt terug
  als `nl`.
- **Vrije accounts kunnen geen bibliotheekstemmen via de API gebruiken.** Dat raakt de
  pratende agent, niet de luisteraar, maar het is goed om te weten: de Vlaamse stem die
  in [elevenlabs-agent.md](elevenlabs-agent.md) staat, werkt alleen als de workspace een
  betaald plan heeft. PCM-uitvoer werkt wél op het gratis plan; de 402 die je daarbij
  ziet gaat over de stem, niet over het formaat.

## Extractie

Scribe levert tekst en verder niets — data collection is een Agents-functie en bestaat
hier niet. De vijf velden moeten wij eruit halen. `segment_collector.py` heeft daarvoor
twee smaken:

- `--extractor gemini` — de echte. Dezelfde velddefinities als in
  [elevenlabs-agent.md](elevenlabs-agent.md) §4, nu als prompt met een JSON-schema en
  `temperature=0`. Vereist `GCP_PROJECT` en application default credentials.
- `--extractor rules` — deterministisch, geen credentials. Herkent "met X van Y", kiest
  de categorie op trefwoorden en de urgentie op tijdswoorden. **Dit is een vangnet, geen
  eindproduct**: het werkt op een beller die zich netjes voorstelt en verder niet.

De gemini-variant is getest in het Qwiklabs-project (2026-09-30) en daar geblokkeerd:
de org policy `constraints/vertexai.allowedModels` staat op `denyAll`, dus elk
Gen AI-model geeft `400 FAILED_PRECONDITION` (getest: `gemini-2.5-flash`, `-flash-lite`,
`-pro`). Auth, project en Vertex-API werken wel; de code zelf is dus niet het probleem.
Voor de demo draait de verzamelaar op `--extractor rules`. De gemini-variant werkt pas
in een GCP-project waar Vertex-modellen toegestaan zijn.

## Draaien

```
pip install -r scripts/requirements.txt

# verzamelaar, stuurt elke update door naar de backend
python scripts/segment_collector.py --port 8600 --forward-url http://localhost:8080/demo/simulate-call

# luisteraar, één per spreker
python scripts/scribe_listen.py --audio samples/audio/vakantiegeld_beurt1.pcm \
    --call-id demo1 --speaker beller --push-url http://localhost:8600/segment
```

Draai de drie beurten uit `samples/audio/` na elkaar met hetzelfde `--call-id` en kijk op
`http://localhost:8600/state/demo1`. Na beurt 1 staan naam en bedrijf er, na beurt 2
springt de categorie op `vakantiegeld`, na beurt 3 gaat de urgentie naar `hoog`. Dat is
het demo-verhaal in drie stappen, zonder dat er iemand hoeft te bellen.

## Op Cloud Run

`infra/deploy_cloudrun.sh` zet de verzamelaar als service `callsight-listener` neer, naast de
backend en het dashboard. De pagina kiest de spreker uit het pad: `/medewerker` en `/beller`,
met `?gesprek=<id>` voor een gedeeld gesprek-id. Het dashboard toont beide als knop in de kop,
met één id per keer dat het dashboard laadt.

- Eén instance (`--max-instances=1`): de gesprekken staan in het geheugen van de verzamelaar.
- `ELEVENLABS_API_KEY` komt uit Secret Manager; de browser krijgt alleen single-use tokens.
- Elke zin stuurt een update naar `/demo/simulate-call`, die er een nieuwe call van maakt. Het
  dashboard toont dus per zin een momentopname; de bovenste is de meest volledige. Eén call die
  live bijwerkt vraagt de live-route uit [contract-live.md](contract-live.md).

## Wat er nog niet is

- De browserpagina die een echte microfoon streamt. Het protocol is bewezen met
  bestandsaudio; de stap naar `getUserMedia` is klein maar nog niet gezet.
- Het token-endpoint voor client-side gebruik.
- De gemini-extractor in een project dat Vertex-modellen toelaat (Qwiklabs: `denyAll`).
- Twee sessies tegelijk, met de medewerker op de tweede.
