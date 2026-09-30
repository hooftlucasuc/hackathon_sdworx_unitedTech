"""Zoek de seed-bedrijven op in de KBO Open Data en schrijf de treffers naar data/seed/kbo.json.

Alleen rechtspersonen: eenmanszaken zijn natuurlijke personen, hun naam is een persoonsgegeven, dus daarvan
wordt niets bewaard. Treft een fictief seed-bedrijf toch een eenmanszaak, dan meldt het script dat enkel als
waarschuwing (hernoem dan het fictieve bedrijf).

  python scripts/kbo_lookup.py ~/Downloads/KboOpenData_0498_2026_09_30_Full.zip

De zip (±300 MB, 2,2 GB uitgepakt) komt niet in de repo; kbo.json wel (enkele regels publieke bedrijfsgegevens).
Bron: KBO Open Data, FOD Economie.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.pipeline import LEGAL_FORMS, _ascii_words  # noqa: E402

OUT = REPO_ROOT / "data" / "seed" / "kbo.json"
log = logging.getLogger("kbo_lookup")


def key_for(name: str) -> str:
    """Zelfde sleutel als company_id_for, ook voor rechtsvormen met puntjes (B.V., v.z.w.; zie PR #3)."""
    words = _ascii_words(name)

    def form_len(at_end: bool) -> int:
        for k in (4, 3, 2, 1):
            if len(words) > k:
                part = words[-k:] if at_end else words[:k]
                if "".join(part) in LEGAL_FORMS and (k == 1 or all(len(w) <= 4 for w in part)):
                    return k
        return 0

    while k := form_len(at_end=True):
        del words[-k:]
    while k := form_len(at_end=False):
        del words[:k]
    return "-".join(words)[:80].strip("-")


def rows(archive: zipfile.ZipFile, name: str):
    with archive.open(name) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
        next(reader)
        yield from reader


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("zip", type=Path, help="KboOpenData_<nr>_<datum>_Full.zip")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    companies = json.loads((REPO_ROOT / "data" / "seed" / "companies.json").read_text(encoding="utf-8"))
    targets = {key_for(c["name"]): c["name"] for c in companies}
    archive = zipfile.ZipFile(args.zip)
    meta = dict(rows(archive, "meta.csv"))

    enterprises = {num: (typ, form, start) for num, status, _sit, typ, form, _cac, start in rows(archive, "enterprise.csv")}
    found: dict[str, dict[str, str]] = defaultdict(dict)
    natural: dict[str, int] = defaultdict(int)
    for num, _lang, _type, denom in rows(archive, "denomination.csv"):
        key = key_for(denom)
        if key not in targets or num not in enterprises:  # niet gezocht, of een vestigingsnummer
            continue
        if enterprises[num][0] == "2":
            found[key].setdefault(num, denom)
        else:
            natural[key] += 1
    for key, n in natural.items():
        log.warning("%s treft %d eenmanszaak/-zaken: hernoem dit fictieve bedrijf", targets[key], n)

    wanted = {num for matches in found.values() for num in matches}
    codes = {(cat, code): desc for cat, code, lang, desc in rows(archive, "code.csv") if lang == "NL"}
    nace: dict[str, dict[str, str]] = {}
    for num, _group, version, code, cls in rows(archive, "activity.csv"):
        if num in wanted and cls == "MAIN" and (num not in nace or version > nace[num]["version"]):
            nace[num] = {"version": version, "code": code, "description": codes.get((f"Nace{version}", code), "")}
    seat: dict[str, dict[str, str]] = {}
    for r in rows(archive, "address.csv"):
        if r[0] in wanted and r[1] == "REGO":
            seat[r[0]] = {"zipcode": r[4], "municipality": r[5] or r[6], "country": r[2] or "België"}

    result = {}
    for key, name in targets.items():
        matches = []
        for num, denom in sorted(found.get(key, {}).items()):
            _typ, form, start = enterprises[num]
            matches.append({
                "enterprise_number": num, "name": denom,
                "juridical_form": codes.get(("JuridicalForm", form), form), "start_date": start,
                "seat": seat.get(num), "main_activity": nace.get(num),
            })
        result[key] = matches
        log.info("%-28s %d rechtspersoon/-personen in de KBO", name, len(matches))

    OUT.write_text(json.dumps({
        "source": "KBO Open Data, FOD Economie",
        "snapshot": meta.get("SnapshotDate"),
        "extract_number": meta.get("ExtractNumber"),
        "companies": result,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("geschreven: %s", OUT.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
