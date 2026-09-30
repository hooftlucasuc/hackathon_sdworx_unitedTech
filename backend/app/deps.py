"""FastAPI dependencies. Store and embedder are created lazily so importing the app never touches GCP."""

from __future__ import annotations

import hmac
import json
import logging
import threading

from fastapi import HTTPException, Request, status

from app.config import Settings

log = logging.getLogger(__name__)
_lock = threading.RLock()  # get_store calls get_embedder while holding it


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_embedder(request: Request):
    state = request.app.state
    if state.embedder is None:
        with _lock:
            if state.embedder is None:
                from app.embeddings import make_embedder

                state.embedder = make_embedder(state.settings)
    return state.embedder


def get_store(request: Request):
    state = request.app.state
    if state.store is None:
        with _lock:
            if state.store is None:
                from app.store import make_store

                store = make_store(state.settings)
                if state.settings.store_backend == "memory":
                    _seed_memory(store, get_embedder(request), state.settings)
                state.store = store
    return state.store


def _seed_memory(store, embedder, settings: Settings) -> None:
    path = settings.memory_seed_file
    if not path or not path.exists():
        return
    from app.pipeline import load_solutions

    rows = json.loads(path.read_text(encoding="utf-8"))
    n = load_solutions(store, embedder, rows)
    log.info("memory store seeded with %d solutions from %s", n, path.name)


def require_api_key(request: Request) -> None:
    expected = request.app.state.settings.api_key
    if not expected:
        return
    given = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing X-API-Key")
