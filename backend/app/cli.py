"""Admin CLI, run from backend/ with GCP credentials (Cloud Shell or `gcloud auth application-default login`).

  python -m app.cli check                          # Vertex embedding + Firestore reachable?
  python -m app.cli load-solutions samples/solutions.json [--reset --yes]
  python -m app.cli load-calls data/seed/calls.json  # historical calls through the same pipeline
  python -m app.cli rescore <call_id>              # recompute suggestions after new solutions

D's seed script can also import the shared pieces directly instead of shelling out:
  from app.pipeline import company_id_for, caller_id_for, slugify, load_solutions, load_calls
  from app.embeddings import make_embedder, TASK_QUERY, TASK_DOCUMENT
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from app.config import get_settings
from app.embeddings import TASK_QUERY, make_embedder
from app.pipeline import load_calls, load_solutions, rescore_call
from app.store import make_store

log = logging.getLogger("callsight.cli")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="embed a test sentence and count solutions")
    p_load = sub.add_parser("load-solutions", help="embed and upsert solutions from a JSON list")
    p_load.add_argument("file", type=Path)
    p_load.add_argument("--reset", action="store_true", help="delete all solutions first")
    p_load.add_argument("--yes", action="store_true", help="confirm --reset")
    p_calls = sub.add_parser("load-calls", help="store historical calls (ElevenLabs payload format) via the pipeline")
    p_calls.add_argument("file", type=Path)
    p_rescore = sub.add_parser("rescore", help="recompute suggestions for one call")
    p_rescore.add_argument("call_id")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    store = make_store(settings)
    embedder = make_embedder(settings)

    if args.cmd == "check":
        vec = embedder.embed(["Het vakantiegeld van een bediende klopt niet"], TASK_QUERY)[0]
        log.info("embedding ok: model=%s dims=%d", settings.embedding_model, len(vec))
        log.info("firestore ok: %d solutions in the knowledge base", store.count_solutions())
        return 0

    if args.cmd == "load-solutions":
        rows = json.loads(args.file.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            log.error("%s must contain a JSON list", args.file)
            return 2
        if args.reset:
            if not args.yes:
                log.error("--reset deletes every solution; add --yes to confirm")
                return 2
            log.info("deleted %d solutions", store.delete_all_solutions())
        log.info("loaded %d solutions from %s", load_solutions(store, embedder, rows), args.file)
        return 0

    if args.cmd == "load-calls":
        rows = json.loads(args.file.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            log.error("%s must contain a JSON list of payloads", args.file)
            return 2
        stats = load_calls(store, embedder, rows, settings.escalation_threshold)
        log.info("calls: %(created)d created, %(skipped)d already present, %(resolved)d resolved", stats)
        return 0

    if args.cmd == "rescore":
        suggestions = rescore_call(store, args.call_id, threshold=settings.escalation_threshold)
        for s in suggestions:
            log.info("%3d  %s", s["score"], s["solution_id"])
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
