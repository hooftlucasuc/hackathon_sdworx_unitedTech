"""Genereer stemfragmenten voor de video en de demo-gesprekken.

Twee bronnen, telkens rechtstreeks uit de markdown (na een tekstwijziging volstaat opnieuw draaien):
  verteller  de `> `-regels onder elke **VO** in docs/video-script.md
  --caller   de beurten van Lindsey in docs/demo-script.md (`> **L1 · wanneer:** tekst`, R1… als reserve)

Engines:
  say         macOS-stem (standaard Ellen, nl_BE). Gratis en lokaal: voor klad, timing en repetitie.
  elevenlabs  ElevenLabs text-to-speech. Voor de eindversie en de live call. Key uit ELEVENLABS_API_KEY
              (omgeving of .env in de repo-root); de key wordt nooit gelogd.

Gebruik:
  python3 scripts/voiceover.py --caller                                   # Lindsey, klad met Ellen
  python3 scripts/voiceover.py --caller --engine elevenlabs --voice-id <id> --verify
  python3 scripts/voiceover.py                                            # verteller
  python3 scripts/voiceover.py --dry-run [--caller]                       # alleen de teksten tonen

Uitvoer in media/vo/<engine>/ (staat in .gitignore):
  verteller  scene<N>-<k>.<ext> en all.<ext>
  --caller   lindsey-<L1|R1…>.<ext>, lindsey-all.<ext> (L-beurten achter elkaar) en lindsey.html (afspeelknoppen)
--verify laat elk bellerfragment terug transcriberen door ElevenLabs speech-to-text, om te controleren of
naam en bedrijf goed verstaan worden; de agent gebruikt een eigen herkenning, dus dit is een benadering.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VIDEO_SCRIPT = REPO_ROOT / "docs" / "video-script.md"
DEMO_SCRIPT = REPO_ROOT / "docs" / "demo-script.md"
OUT_ROOT = REPO_ROOT / "media" / "vo"
PLACEHOLDER = re.compile(r"\b[XY]\b")
TARGET_SECONDS = 170  # 2:50
MUST_HEAR = ("lindsey", "tafels", "united consulting")  # moet in het transcript van L1 staan
API = "https://api.elevenlabs.io/v1"

# Uitspraakhulp. De macOS-stem leest Engelse woorden met Nederlandse klanken; ElevenLabs doet dat beter.
PRONUNCIATION = {
    "say": {"CallSight": "Kolsait", "SD Worx": "es dee works", "ElevenLabs": "Elevenlebs", "United": "Joenaitid",
            "Comp & Ben": "komp en ben", "Aikido": "Aikiedo", "een AI": "een aa-ie"},
    "elevenlabs": {"Comp & Ben": "Comp and Ben"},
}
# Standaardstemmen: Ellen (nl_BE, vrouw) lokaal; bij ElevenLabs een meertalige premade-stem als vertrekpunt.
# Kies voor de eindversie liefst een Vlaamse stem uit de Voice Library en geef die mee met --voice-id.
DEFAULT_VOICE_ID = {"narrator": "JBFqnCBsd6RMkjVDRZzb", "caller": "EXAVITQu4vr4xnSDxMaL"}

log = logging.getLogger("voiceover")


@dataclass
class Clip:
    name: str
    title: str
    text: str


def parse_narrator(markdown: str) -> list[Clip]:
    clips: list[Clip] = []
    scene, title, index = 0, "", 0
    in_vo, buffer = False, []

    def flush() -> None:
        nonlocal buffer, index
        if buffer:
            index += 1
            clips.append(Clip(f"scene{scene}-{index}", title, " ".join(buffer)))
        buffer = []

    for line in markdown.splitlines():
        heading = re.match(r"^## Scène (\d+) · (.+?)(?: \(|$)", line)
        if heading:
            flush()
            scene, title, index, in_vo = int(heading.group(1)), heading.group(2), 0, False
            continue
        if not scene:
            continue
        if line.startswith("**VO"):
            flush()
            in_vo = True
        elif in_vo and line.startswith(">"):
            buffer.append(line.lstrip("> ").strip())
        elif (in_vo and not line.strip() and buffer) or line.startswith(("**", "## ")):
            flush()
            in_vo = False
    flush()
    return clips


def parse_caller(markdown: str) -> list[Clip]:
    pattern = re.compile(r"^> \*\*([LR]\d+) · (.+?):\*\* (.+)$")
    return [Clip(f"lindsey-{m.group(1)}", m.group(2), m.group(3).strip())
            for m in map(pattern.match, markdown.splitlines()) if m]


def prepare(text: str, engine: str) -> str:
    text = text.replace("níet", "niet")
    for word, spoken in PRONUNCIATION[engine].items():
        text = text.replace(word, spoken)
    return text.replace("&", "en")


def synth_say(text: str, out: Path, voice: str, rate: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "clip.aiff"
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff), text], check=True)
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", str(aiff), str(out)], check=True)


def api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    env_file = REPO_ROOT / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("ELEVENLABS_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY ontbreekt: zet hem in .env (staat in .gitignore) of in je omgeving.")
    return key


def _post(url: str, key: str, body: bytes, content_type: str, accept: str) -> bytes:
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"xi-api-key": key, "Content-Type": content_type, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:300]
        raise SystemExit(f"ElevenLabs gaf {err.code}: {detail}") from None


def synth_elevenlabs(text: str, out: Path, key: str, voice_id: str, model: str) -> None:
    body = json.dumps({"text": text, "model_id": model,
                       "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}).encode()
    out.write_bytes(_post(f"{API}/text-to-speech/{voice_id}?output_format=mp3_44100_128", key, body,
                          "application/json", "audio/mpeg"))


def transcribe(path: Path, key: str, model: str) -> str:
    boundary = uuid.uuid4().hex
    fields = {"model_id": model, "language_code": "nl"}
    head = "".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields.items())
    head += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
             "Content-Type: application/octet-stream\r\n\r\n")
    body = head.encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    raw = _post(f"{API}/speech-to-text", key, body, f"multipart/form-data; boundary={boundary}", "application/json")
    return json.loads(raw).get("text", "")


def duration(path: Path) -> float:
    info = subprocess.run(["afinfo", str(path)], capture_output=True, text=True, check=False).stdout
    match = re.search(r"estimated duration: ([\d.]+)", info)
    return float(match.group(1)) if match else 0.0


def concat(files: list[Path], out: Path, pause: float) -> None:
    """Clips achter elkaar met een pauze ertussen, om in één keer te beluisteren."""
    if not shutil.which("ffmpeg") or not files:
        return
    inputs, filters = [], []
    for i, f in enumerate(files):
        inputs += ["-i", str(f)]
        filters.append(f"[{i}:a]aresample=44100,apad=pad_dur={pause}[a{i}]")
    graph = ";".join(filters) + ";" + "".join(f"[a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=0:a=1[out]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[out]", str(out)],
                   check=True)


def soundboard(clips: list[tuple[Clip, Path]], out: Path) -> None:
    """Lokale afspeelpagina: één knop per beurt, toetsen 1-9, een nieuwe klik stopt het vorige fragment."""
    buttons = "\n".join(
        f'<button data-src="{html.escape(p.name)}"><b>{html.escape(c.name.split("-", 1)[1])}</b>'
        f'<span class="when">{html.escape(c.title)}</span><span class="text">{html.escape(c.text)}</span></button>'
        for c, p in clips)
    out.write_text(f"""<!doctype html>
<html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lindsey · afspelen</title>
<style>
  :root {{ color-scheme: light dark; --bg: #f4f4f5; --card: #fff; --text: #27272a; --muted: #71717a; --accent: #2563eb; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #18181b; --card: #27272a; --text: #f4f4f5; --muted: #a1a1aa; }} }}
  body {{ margin: 0; padding: 16px; background: var(--bg); color: var(--text); font: 16px/1.4 system-ui, sans-serif; }}
  h1 {{ font-size: 18px; margin: 0 0 4px; }} p {{ margin: 0 0 16px; color: var(--muted); font-size: 14px; }}
  button {{ display: grid; grid-template-columns: 48px 1fr; gap: 2px 12px; width: 100%; text-align: left;
           margin: 0 0 8px; padding: 12px; border: 2px solid transparent; border-radius: 10px;
           background: var(--card); color: var(--text); font: inherit; cursor: pointer; }}
  button b {{ grid-row: span 2; font-size: 20px; align-self: center; }}
  .when {{ color: var(--muted); font-size: 13px; }} .text {{ font-size: 15px; }}
  button.playing {{ border-color: var(--accent); }}
</style></head><body>
<h1>Lindsey Tafels · scenario a</h1>
<p>Speel een fragment af zodra de agent zwijgt. Toetsen 1 tot 9 volgen de volgorde; Escape stopt.</p>
{buttons}
<script>
  const audio = new Audio();
  const buttons = [...document.querySelectorAll("button")];
  function play(btn) {{
    buttons.forEach(b => b.classList.remove("playing"));
    audio.pause(); audio.src = btn.dataset.src; audio.currentTime = 0;
    audio.play(); btn.classList.add("playing");
  }}
  audio.addEventListener("ended", () => buttons.forEach(b => b.classList.remove("playing")));
  buttons.forEach(b => b.addEventListener("click", () => play(b)));
  document.addEventListener("keydown", e => {{
    if (e.key === "Escape") {{ audio.pause(); buttons.forEach(b => b.classList.remove("playing")); }}
    const i = Number(e.key) - 1;
    if (i >= 0 && i < buttons.length) play(buttons[i]);
  }});
</script></body></html>
""", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--caller", action="store_true", help="Lindsey's beurten uit het demo-script")
    parser.add_argument("--engine", choices=("say", "elevenlabs"), default="say")
    parser.add_argument("--voice", default="Ellen", help="macOS-stem (say)")
    parser.add_argument("--rate", type=int, default=170, help="woorden per minuut (say)")
    parser.add_argument("--voice-id", help="ElevenLabs voice-ID (standaard een premade-stem)")
    parser.add_argument("--model", default="eleven_multilingual_v2", help="ElevenLabs TTS-model")
    parser.add_argument("--stt-model", default="scribe_v1", help="ElevenLabs speech-to-text-model voor --verify")
    parser.add_argument("--verify", action="store_true", help="bellerfragmenten laten transcriberen (ElevenLabs-key nodig)")
    parser.add_argument("--only", action="append", help="alleen deze clip(s), bv. scene3 of L1")
    parser.add_argument("--dry-run", action="store_true", help="alleen de teksten tonen")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    role = "caller" if args.caller else "narrator"
    source = DEMO_SCRIPT if args.caller else VIDEO_SCRIPT
    clips = (parse_caller if args.caller else parse_narrator)(source.read_text(encoding="utf-8"))
    if args.only:
        clips = [c for c in clips if any(o in c.name for o in args.only)]
    if not clips:
        raise SystemExit(f"geen fragmenten gevonden in {source.relative_to(REPO_ROOT)}")

    out_dir = OUT_ROOT / args.engine
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = "m4a" if args.engine == "say" else "mp3"
    needs_key = not args.dry_run and (args.engine == "elevenlabs" or args.verify)
    key = api_key() if needs_key else ""
    voice_id = args.voice_id or DEFAULT_VOICE_ID[role]

    made: list[tuple[Clip, Path]] = []
    total = 0.0
    for clip in clips:
        if PLACEHOLDER.search(clip.text):
            log.warning("%-11s overgeslagen: bevat nog een placeholder (X/Y)", clip.name)
            continue
        text = prepare(clip.text, args.engine)
        if args.dry_run:
            log.info("%-11s %s", clip.name, text)
            continue
        out = out_dir / f"{clip.name}.{ext}"
        if args.engine == "say":
            synth_say(text, out, args.voice, args.rate)
        else:
            synth_elevenlabs(text, out, key, voice_id, args.model)
        seconds = duration(out)
        total += seconds
        made.append((clip, out))
        log.info("%-11s %5.1f s  %s", clip.name, seconds, clip.title)

    if not made:
        return 0
    if args.caller:
        turns = [p for c, p in made if "-L" in c.name]
        concat(turns, out_dir / f"lindsey-all.{ext}", pause=2.5)
        soundboard(made, out_dir / "lindsey.html")
        log.info("totaal Lindsey: %.0f s spreektijd; afspeelpagina: %s", total,
                 (out_dir / "lindsey.html").relative_to(REPO_ROOT))
    else:
        concat([p for _, p in made], out_dir / f"all.{ext}", pause=0.6)
        log.info("totaal VO: %.0f s (video-doel %d s; de rest is gesprek en beeld)", total, TARGET_SECONDS)
    log.info("bestanden in %s", out_dir.relative_to(REPO_ROOT))

    if args.verify and args.caller:
        for clip, path in made:
            heard = transcribe(path, key, args.stt_model)
            log.info("%-11s gehoord: %s", clip.name, heard)
            if clip.name.endswith("-L1"):
                missing = [w for w in MUST_HEAR if w not in heard.lower()]
                if missing:
                    log.warning("L1: niet verstaan: %s. Pas de uitspraak aan of vraag A om ASR-keywords in de agent.",
                                ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
