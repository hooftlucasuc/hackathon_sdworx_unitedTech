# Testaudio

Synthetische audio om de luisteraar te draaien zonder microfoon en zonder TTS-credits.
Raw PCM, 16-bit signed little-endian, mono, 16 kHz — het formaat dat
`scripts/scribe_listen.py` verwacht.

De drie bestanden zijn drie beurten van hetzelfde fictieve gesprek. Draai ze na elkaar
met hetzelfde `--call-id` om te zien hoe de velden zich vullen terwijl het gesprek loopt.

| Bestand | Inhoud | Wat het toevoegt |
|---|---|---|
| `vakantiegeld_beurt1.pcm` | "Goeiedag, met Sofie Janssens van Bakkerij Verhulst BV." | naam en bedrijf |
| `vakantiegeld_beurt2.pcm` | de uitleg van het probleem | probleem en categorie |
| `vakantiegeld_beurt3.pcm` | "Het is echt dringend..." | urgentie springt naar hoog |

Gemaakt met ElevenLabs TTS (premade stem Sarah, `eleven_flash_v2_5`). Beller en bedrijf
zijn verzonnen, zoals de projectregel vereist. Dit is geen opgenomen gesprek: de regel
"geen audio bewaren" gaat over gespreksopnames met persoonsgegevens, en die staan hier
niet en horen hier nooit te komen.
