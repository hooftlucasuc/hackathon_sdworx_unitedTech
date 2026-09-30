"""Seed Firestore met de fictieve CallSight-dataset uit data/seed/.

Datums staan als `days_ago` in de JSON en worden hier omgerekend ten opzichte van nu, zodat recency
op de demodag klopt. Tellers (call_count, open_issues, times_used, times_successful, last_used_at)
worden uit de calls afgeleid, zodat alles onderling consistent is.

Gebruik (vanuit de repo-root, met de backend-venv actief):
  python scripts/seed.py --check              # alleen valideren, geen GCP nodig
  python scripts/seed.py --reset              # collecties wissen en opnieuw vullen (Vertex-embeddings)
  python scripts/seed.py --reset --offline    # zelfde, maar met de hash-embedder (niet semantisch)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.ids import caller_id, company_id  # noqa: E402

SEED_DIR = REPO_ROOT / "data" / "seed"
COLLECTIONS = ("companies", "callers", "calls", "solutions")
CATEGORIES = {"vakantiegeld", "loonberekening", "ziekte", "dimona", "maaltijdcheques", "bedrijfswagen", "ontslag", "overig"}
URGENCIES = {"laag", "midden", "hoog"}

log = logging.getLogger("seed")


def load(name: str) -> list[dict[str, Any]]:
    return json.loads((SEED_DIR / f"{name}.json").read_text(encoding="utf-8"))


def validate(companies, callers, solutions, calls, experts) -> list[str]:
    errors: list[str] = []
    company_names = {c["name"] for c in companies}
    caller_keys = {(c["name"], c["company"]) for c in callers}
    solution_ids = {s["id"] for s in solutions}
    expert_ids = {e["id"] for e in experts}
    if len({company_id(n) for n in company_names}) != len(company_names):
        errors.append("twee bedrijven krijgen hetzelfde company_id")
    for c in callers:
        if c["company"] not in company_names:
            errors.append(f"beller {c['name']}: onbekend bedrijf {c['company']}")
    for s in solutions:
        if s["category"] not in CATEGORIES:
            errors.append(f"{s['id']}: onbekende category {s['category']}")
        if s["owner"] and s["owner"] not in expert_ids:
            errors.append(f"{s['id']}: onbekende owner {s['owner']}")
        if s["prior_successful"] > s["prior_used"]:
            errors.append(f"{s['id']}: prior_successful > prior_used")
        for other in s["conflicts_with"]:
            if other not in solution_ids:
                errors.append(f"{s['id']}: conflicts_with onbekend {other}")
    by_id = {s["id"]: s for s in solutions}
    for i, call in enumerate(calls):
        where = f"call #{i} ({call['caller']})"
        if (call["caller"], call["company"]) not in caller_keys:
            errors.append(f"{where}: beller niet in callers.json")
        if call["category"] not in CATEGORIES or call["urgency"] not in URGENCIES:
            errors.append(f"{where}: ongeldige category of urgency")
        if call["solution"] is not None:
            if call["solution"] not in solution_ids:
                errors.append(f"{where}: onbekende solution {call['solution']}")
            elif by_id[call["solution"]]["category"] != call["category"]:
                errors.append(f"{where}: category wijkt af van {call['solution']}")
        if (call["solution"] is None) != (call["worked"] is None):
            errors.append(f"{where}: open call heeft solution en worked allebei null")
    return errors


def build(companies, callers, solutions, calls, experts, now: datetime) -> dict[str, dict[str, dict]]:
    """Alle documenten, per collectie, zonder embeddings."""
    ago = lambda days: now - timedelta(days=days)  # noqa: E731
    experts_by_id = {e["id"]: e for e in experts}
    company_country = {c["name"]: c["country"] for c in companies}

    docs: dict[str, dict[str, dict]] = {name: {} for name in COLLECTIONS}

    for c in companies:
        docs["companies"][company_id(c["name"])] = {
            "name": c["name"], "sector": c["sector"], "size": c["size"], "country": c["country"],
            "first_seen": None, "last_seen": None, "call_count": 0, "open_issues": 0,
        }
    for c in callers:
        cid = company_id(c["company"])
        docs["callers"][caller_id(c["name"], cid)] = {
            "name": c["name"], "company_id": cid, "first_seen": None, "last_seen": None, "call_count": 0,
        }
    for s in solutions:
        owner = experts_by_id.get(s["owner"]) if s["owner"] else None
        docs["solutions"][s["id"]] = {
            "title": s["title"], "problem_text": s["problem_text"], "solution_text": s["solution_text"],
            "category": s["category"],
            "times_used": s["prior_used"], "times_successful": s["prior_successful"],
            "last_used_at": ago(s["last_used_days_ago"]) if s["last_used_days_ago"] is not None else None,
            "source_call_id": None,
            # trust-signalen (additief op het contract; B en C mogen ze negeren)
            "country": s["country"], "source": s["source"],
            "owner_expert": {"id": owner["id"], "name": owner["name"], "team": owner["team"]} if owner else None,
            "last_reviewed_at": ago(s["last_reviewed_days_ago"]) if s["last_reviewed_days_ago"] is not None else None,
            "conflicts_with": s["conflicts_with"],
        }

    for i, call in enumerate(sorted(calls, key=lambda c: -c["days_ago"])):
        started = ago(call["days_ago"])
        cid = company_id(call["company"])
        pid = caller_id(call["caller"], cid)
        call_id = f"seed-{i:03d}"
        resolved = call["solution"] is not None
        docs["calls"][call_id] = {
            "caller_id": pid, "company_id": cid, "started_at": started, "duration_secs": call["duration"],
            "problem": call["problem"], "category": call["category"], "urgency": call["urgency"],
            "summary": call["problem"], "transcript": [],
            "status": "resolved" if resolved else "open",
            "suggestions": [], "chosen_solution_id": call["solution"],
            "worked": call["worked"], "country": company_country[call["company"]], "seed": True,
        }
        for doc in (docs["companies"][cid], docs["callers"][pid]):
            doc["call_count"] += 1
            doc["first_seen"] = doc["first_seen"] or started
            doc["last_seen"] = started
        if not resolved:
            docs["companies"][cid]["open_issues"] += 1
            continue
        sol = docs["solutions"][call["solution"]]
        sol["times_used"] += 1
        sol["times_successful"] += int(bool(call["worked"]))
        if sol["last_used_at"] is None or started > sol["last_used_at"]:
            sol["last_used_at"] = started

    # Bedrijven/bellers zonder calls krijgen toch een first_seen, anders sorteert het dashboard ze raar.
    for name in ("companies", "callers"):
        for doc in docs[name].values():
            doc["first_seen"] = doc["first_seen"] or ago(400)
            doc["last_seen"] = doc["last_seen"] or doc["first_seen"]
    return docs


def embed_all(docs: dict[str, dict[str, dict]], offline: bool) -> None:
    from google.cloud.firestore_v1.vector import Vector

    from app.config import get_settings
    from app.store.embeddings import TASK_DOCUMENT, TASK_QUERY, HashEmbedder, VertexEmbedder

    settings = get_settings()
    if offline:
        embedder = HashEmbedder(settings.embedding_dim)
    else:
        embedder = VertexEmbedder(settings.gcp_project, settings.gcp_region, settings.embedding_model, settings.embedding_dim)
    # Zelfde task types als de backend (TEAMPLAN: RETRIEVAL_DOCUMENT voor solutions, RETRIEVAL_QUERY voor calls).
    for name, field, task in (("solutions", "problem_text", TASK_DOCUMENT), ("calls", "problem", TASK_QUERY)):
        ids = list(docs[name])
        vectors = embedder.embed([docs[name][i][field] for i in ids], task)
        for doc_id, vec in zip(ids, vectors):
            docs[name][doc_id]["problem_embedding"] = Vector(vec)
        log.info("%d %s geëmbed", len(ids), name)


def write(docs: dict[str, dict[str, dict]], reset: bool) -> None:
    from google.cloud import firestore

    from app.config import get_settings

    db = firestore.Client(project=get_settings().gcp_project or None)
    if reset:
        for name in COLLECTIONS:
            deleted = 0
            for snap in db.collection(name).list_documents(page_size=300):
                snap.delete()
                deleted += 1
            log.info("%s: %d documenten gewist", name, deleted)
    for name, items in docs.items():
        batch, n = db.batch(), 0
        for doc_id, data in items.items():
            batch.set(db.collection(name).document(doc_id), data)
            n += 1
            if n % 400 == 0:
                batch.commit()
                batch = db.batch()
        batch.commit()
        log.info("%s: %d documenten geschreven", name, n)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="alleen valideren en samenvatten")
    parser.add_argument("--reset", action="store_true", help="collecties eerst wissen (ook demo-calls)")
    parser.add_argument("--offline", action="store_true", help="hash-embedder in plaats van Vertex")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    data = {name: load(name) for name in ("companies", "callers", "solutions", "calls", "experts")}
    errors = validate(**data)
    if errors:
        for e in errors:
            log.error(e)
        return 1
    docs = build(**data, now=datetime.now(timezone.utc))
    with_history = [d["name"] for d in docs["callers"].values() if d["call_count"] >= 3]
    log.info(
        "ok: %d bedrijven, %d bellers, %d solutions, %d calls (%d open); bellers met >=3 calls: %s",
        len(docs["companies"]), len(docs["callers"]), len(docs["solutions"]), len(docs["calls"]),
        sum(d["status"] == "open" for d in docs["calls"].values()), ", ".join(with_history),
    )
    if args.check:
        return 0
    embed_all(docs, offline=args.offline)
    write(docs, reset=args.reset)
    return 0


if __name__ == "__main__":
    sys.exit(main())
