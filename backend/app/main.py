"""FastAPI app factory. Run: uvicorn app.main:app --port 8080"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import api, webhook
from app.config import Settings, get_settings


def create_app(settings: Optional[Settings] = None, store=None, embedder=None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(levelname)s %(name)s: %(message)s")

    app = FastAPI(title="CallSight backend", version="0.1.0")
    app.state.settings = settings
    app.state.store = store
    app.state.embedder = embedder

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
    )
    app.include_router(webhook.router)
    app.include_router(api.router)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict:
        return {"status": "ok", "store": settings.store_backend, "demo_mode": settings.demo_mode}

    return app


app = create_app()
