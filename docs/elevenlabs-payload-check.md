# Docs-check ElevenLabs — payloadvelden en signature

Rol A, 2026-09-30. Gecontroleerd tegen de actuele ElevenLabs-docs en tegen de
broncode van de Python-SDK (`elevenlabs` 2.70.0). Conclusie vooraf: **het
contract in `TEAMPLAN.md` §1.2 klopt.** Geen wijziging nodig. Wel zes details
die B moet afvangen en één uitbreiding die A gebruikt.

Bronnen:
- `https://elevenlabs.io/docs/eleven-agents/workflows/post-call-webhooks` (voeg `.md` toe aan elke docs-URL voor schone markdown)
- `https://elevenlabs.io/docs/eleven-agents/api-reference/conversations/get` — typedefinities van de payload
- `https://elevenlabs.io/docs/eleven-agents/api-reference/agents/create` — `AnalysisProperty`, `EvaluationSettingsInput`
- `elevenlabs` 2.70.0, bestand `elevenlabs/webhooks_custom.py` — de echte signature-verificatie

De docs staan sinds kort onder `/docs/eleven-agents/…` (was `conversational-ai`,
daarna `agents-platform`). Oude links redirecten nog.

## 1. Bevestigd

| Contract §1.2 | Status |
|---|---|
| Header `ElevenLabs-Signature` | correct (HTTP-headers zijn hoofdletterongevoelig; in FastAPI lees je `elevenlabs-signature`) |
| `t=<ts>,v0=<hmac>`, HMAC-SHA256 over `"<ts>.<body>"` | correct, zie §2 |
| `type: "post_call_transcription"` | correct |
| `data.conversation_id`, `data.agent_id`, `data.status` | correct |
| `data.transcript[]` met `role` (`user`\|`agent`), `message`, `time_in_call_secs` | correct |
| `data.metadata.start_time_unix_secs`, `data.metadata.call_duration_secs` | correct, beide verplicht en integer |
| `data.analysis.transcript_summary` | correct, verplicht |
| `data.analysis.data_collection_results.<veld>.value` | correct, maar zie §3.2 |

## 2. Signature — exact zoals de SDK het doet

Uit `webhooks_custom.py`, letterlijk de logica:

```python
parts = sig_header.split(",")                  # volgorde ligt niet vast
timestamp = next(p[2:] for p in parts if p.startswith("t="))
signature = next(p for p in parts if p.startswith("v0="))   # inclusief prefix

message = f"{timestamp}.{raw_body}"            # raw body, niet de geparste JSON
digest  = "v0=" + hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
```

Vier dingen die eruit volgen:

1. De vergelijking gaat over de **volledige** string inclusief `v0=`.
2. `raw_body` is de onbewerkte bytes van het request. Parse nooit eerst naar JSON
   en serialiseer terug — dat verandert de whitespace en breekt de hash.
3. Tolerantie is **30 minuten**, en alleen aan de oude kant: een timestamp uit de
   toekomst wordt niet geweigerd. Ons replay-script zet dus altijd een verse `t=`.
4. De SDK vergelijkt met `!=`. Wij gebruiken `hmac.compare_digest` — even duur,
   geen timing-lek.

De backend heeft de SDK hiervoor niet nodig; zes regels stdlib volstaan. Let op:
`construct_event` zit in de Python-SDK **niet** in `elevenlabs/webhooks/`, maar in
`elevenlabs/webhooks_custom.py`, met parameters `rawBody`, `sig_header`, `secret`
(niet `payload`/`signature`). Wie hem toch wil gebruiken: dat zijn de namen.

## 3. Zes punten voor B

### 3.1 Er komen drie soorten webhooks op dezelfde URL
`post_call_transcription`, `post_call_audio` (base64-audio) en
`call_initiation_failure`. Check `type` als eerste en negeer de rest met een 200.
Een audio-payload door de transcriptie-parser halen geeft een crash — en wij
bewaren sowieso geen audio, dus die webhook zetten we niet aan.

### 3.2 `data_collection_results.<veld>` is meer dan `value`
```json
{"data_collection_id": "caller_name", "rationale": "…", "name": "caller_name",
 "value": "Sofie Janssens", "json_schema": {…}}
```
`data_collection_id` en `rationale` zijn verplicht, **`value` is optioneel**.
Vindt de LLM het veld niet in het transcript, dan is `value` null of ontbreekt de
sleutel. Dus `.get("value")`, nooit `["value"]`, en een lege `caller_name` moet
door de upsert heen kunnen (val terug op "onbekende beller").

`rationale` is een LLM-zin over waaróm dat de waarde is. Bruikbaar als tooltip in
het dashboard, maar het is persoonsgegeven: niet loggen.

### 3.3 `transcript[].message` mag null zijn
Alleen `role` en `time_in_call_secs` zijn verplicht. Beurten zonder tekst
(tool-calls, genegeerde backchannel) hebben geen `message`. Filter ze eruit voor
je het transcript opslaat.

### 3.4 Retries sturen een identieke payload
Webhook-retries zijn instelbaar en de payload van een retry is niet te
onderscheiden van het origineel. Dedupliceren op `data.conversation_id` +
top-level `event_timestamp` (unix secs, staat naast `type` en `data`). Omdat
`call_id = conversation_id` en we upserten, zijn we hier al grotendeels tegen
bestand — maar de tellers (`call_count`, `times_used`) mogen niet twee keer op.

### 3.5 Een stukgaande endpoint schakelt de webhook uit
Tien opeenvolgende mislukkingen en de webhook wordt automatisch uitgezet;
heraanzetten kan alleen in de settings. Tijdens de demo is dat fataal. Dus:
signature checken, 200 teruggeven, en het zware werk (embedding, vector search)
daarna. De docs noemen geen timeout in seconden — onze 5 s is een eigen budget,
geen ElevenLabs-limiet.

### 3.6 `analysis.call_successful` is een enum
`success` · `failure` · `unknown`. Dat is het ingebouwde oordeel; onze eigen
evaluation criteria komen apart terug in `analysis.evaluation_criteria_results`
met `criteria_id`, `result` en `rationale`.

## 4. Uitbreiding die A gebruikt: enum op data collection

De docs-pagina over data collection noemt vier types (string, boolean, integer,
number) en suggereert dat je een categorie alleen via de beschrijving kunt
sturen. De API kan meer. `AnalysisProperty` bij `POST /v1/convai/agents/create`
heeft ook:

- `enum` — lijst toegestane stringwaarden, wordt aan de LLM meegegeven;
- `allowed_values` — server-side weigering van alles buiten de set, wordt *niet*
  aan de LLM getoond;
- `name`, `llm` (eigen model per veld).

`category` en `urgency` krijgen dus een harde enum in plaats van een hoopvolle
beschrijving. Dat haalt de meeste ruis weg, maar niet alle: het veld kan nog
steeds leeg terugkomen. B blijft dus valideren en valt terug op `overig` /
`midden`.

Verder relevant voor de agentconfig:
- Limiet van 25 data-collection-items per agent (40 op Trial/Enterprise). Wij hebben er 5.
- `platform_settings.summary_language: "nl"` zet samenvatting, titel en rationales
  in het Nederlands. Zonder die instelling raadt ElevenLabs de taal.
- Data collection zit in `platform_settings.data_collection` (map veldnaam →
  `AnalysisProperty`), evaluation criteria in `platform_settings.evaluation.criteria`.

## 5. EU-residency, scherper dan "open punt"

Voor de GDPR-sectie van D. Data residency bestaat bij ElevenLabs, maar:

- Het is een **Enterprise-feature**, met een volledig apart account en een aparte
  workspace: `eu.residency.elevenlabs.io`, API op `api.eu.residency.elevenlabs.io`,
  eigen API-key. Je migreert er niet even naartoe.
- Residency dekt **opslag**. Verwerking kan nog buiten de EU gebeuren. Alleen met
  Zero Retention Mode via de API kun je verwerking tot de EU beperken.
- Zelfs dan noemen de docs post-call webhooks expliciet als uitzondering die tot
  verwerking buiten de regio kan leiden.

Formulering voor de README: *de PoC draait op de standaard (US) omgeving; voor
productie is een Enterprise-account met EU-residency plus Zero Retention Mode
nodig, en dan nog moet per integratie worden nagegaan of er verwerking buiten de
EU plaatsvindt.* Dat is eerlijker dan "EU-residency is een productievoorwaarde"
en het is precies het soort nuance waar een jury naar vraagt.
