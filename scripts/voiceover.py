"""Genereer de voice-over uit docs/video-script.md, één audiobestand per VO-blok.

De tekst komt rechtstreeks uit het videoscript (de `> `-regels onder elke **VO**), dus na een
tekstwijziging volstaat opnieuw draaien. Blokken met een placeholder (X, Y) worden overgeslagen.

Engines:
  say         macOS-stem (standaard Ellen, nl_BE). Gratis en lokaal: voor klad en timing.
  elevenlabs  ElevenLabs text-to-speech. Voor de eindversie. Key uit ELEVENLABS_API_KEY
              (omgeving of .env in de repo-root); de key wordt nooit gelogd.

Gebruik:
  python3 scripts/voiceover.py                                  # klad met Ellen
  python3 scripts/voiceover.py --engine elevenlabs --voice-id <id>
  python3 scripts/voiceover.py --only 3                         # alleen scène 3

Uitvoer: media/vo/<engine>/scene<N>-<k>.<ext> plus alles-achter-elkaar in all.<ext> (met ffmpeg).
"""

from __future__ import annotations

import argparse
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
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "docs" / "video-script.md"
OUT_ROOT = REPO_ROOT / "media" / "vo"
PLACEHOLDER = re.compile(r"\b[XY]\b")
TARGET_SECONDS = 170  # 2:50

# Uitspraakhulp. De macOS-stem leest Engelse merknamen letterlijk; ElevenLabs doet dat beter.
PRONUNCIATION = {
    "say": {"CallSight": "Kolsait", "SD Worx": "es dee works", "ElevenLabs": "Elevenlebs",
            "Comp & Ben": "comp en ben", "Aikido": "Aikiedo", "een AI": "een aa-ie"},
    "elevenlabs": {"Comp & Ben": "Comp and Ben"},
}

log = logging.getLogger("voiceover")


@dataclass
class Clip:
    scene: int
    index: int
    title: str
    text: str

    @property
    def name(self) -> str:
        return f"scene{self.scene}-{self.index}"


def parse(markdown: str) -> list[Clip]:
    clips: list[Clip] = []
    scene, title, index = 0, "", 0
    in_vo, buffer = False, []

    def flush() -> None:
        nonlocal buffer, index
        if buffer:
            index += 1
            clips.append(Clip(scene, index, title, " ".join(buffer)))
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
        elif in_vo and not line.strip() and buffer:
            flush()
            in_vo = False
        elif line.startswith("**") or line.startswith("## "):
            flush()
            in_vo = False
    flush()
    return clips


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


def synth_elevenlabs(text: str, out: Path, key: str, voice_id: str, model: str) -> None:
    body = json.dumps({
        "text": text,
        "model_id": model,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
        data=body, method="POST",
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            out.write_bytes(resp.read())
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:300]
        raise SystemExit(f"ElevenLabs gaf {err.code}: {detail}") from None


def duration(path: Path) -> float:
    info = subprocess.run(["afinfo", str(path)], capture_output=True, text=True).stdout
    match = re.search(r"estimated duration: ([\d.]+)", info)
    return float(match.group(1)) if match else 0.0


def concat(files: list[Path], out: Path) -> None:
    """Alle clips achter elkaar met 0,6 s stilte ertussen, om in één keer te beluisteren."""
    if not shutil.which("ffmpeg") or not files:
        return
    inputs, filters = [], []
    for i, f in enumerate(files):
        inputs += ["-i", str(f)]
        filters.append(f"[{i}:a]aresample=44100,apad=pad_dur=0.6[a{i}]")
    graph = ";".join(filters) + ";" + "".join(f"[a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=0:a=1[out]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[out]", str(out)],
                   check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", choices=("say", "elevenlabs"), default="say")
    parser.add_argument("--voice", default="Ellen", help="macOS-stem (say)")
    parser.add_argument("--rate", type=int, default=170, help="woorden per minuut (say)")
    parser.add_argument("--voice-id", default="JBFqnCBsd6RMkjVDRZzb", help="ElevenLabs voice-ID")
    parser.add_argument("--model", default="eleven_multilingual_v2", help="ElevenLabs-model")
    parser.add_argument("--only", type=int, action="append", help="alleen deze scène(s)")
    parser.add_argument("--dry-run", action="store_true", help="alleen de teksten tonen")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    clips = [c for c in parse(SCRIPT.read_text(encoding="utf-8")) if not args.only or c.scene in args.only]
    out_dir = OUT_ROOT / args.engine
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = "m4a" if args.engine == "say" else "mp3"
    key = api_key() if args.engine == "elevenlabs" and not args.dry_run else ""

    made: list[Path] = []
    total = 0.0
    for clip in clips:
        if PLACEHOLDER.search(clip.text):
            log.warning("%-9s overgeslagen: bevat nog een placeholder (X/Y)", clip.name)
            continue
        text = prepare(clip.text, args.engine)
        if args.dry_run:
            log.info("%-9s %s", clip.name, text)
            continue
        out = out_dir / f"{clip.name}.{ext}"
        if args.engine == "say":
            synth_say(text, out, args.voice, args.rate)
        else:
            synth_elevenlabs(text, out, key, args.voice_id, args.model)
        seconds = duration(out)
        total += seconds
        made.append(out)
        log.info("%-9s %5.1f s  %s", clip.name, seconds, clip.title)

    if made:
        concat(made, out_dir / f"all.{ext}")
        log.info("totaal VO: %.0f s (video-doel %d s; de rest is gesprek en beeld)", total, TARGET_SECONDS)
        log.info("bestanden in %s", out_dir.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
