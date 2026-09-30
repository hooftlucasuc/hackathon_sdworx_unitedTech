"""Settings from environment. Locally from `.env` (repo root or backend/); on Cloud Run from env + Secret Manager."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google Cloud. Empty project = take it from the runtime credentials (Cloud Run metadata server).
    gcp_project: str = ""
    gcp_region: str = "europe-west1"
    firestore_database: str = "(default)"
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768

    # ElevenLabs post-call webhook. Empty secret = every webhook is rejected (fail closed).
    elevenlabs_webhook_secret: str = ""
    webhook_tolerance_secs: int = 1800
    webhook_max_bytes: int = 5 * 1024 * 1024

    # best_score below this (or no suggestion at all) sets escalate=true. D calibrates it on the seed data.
    escalation_threshold: int = 60

    # /demo/simulate-call is only mounted when true.
    demo_mode: bool = False

    # Comma-separated list of dashboard origins allowed by CORS. No wildcard.
    frontend_origin: str = "http://localhost:5173"

    # Optional. When set, every non-webhook route requires header X-API-Key with this value.
    api_key: str = ""

    # firestore (default) | memory (local dev and tests, no GCP needed)
    store_backend: str = "firestore"
    memory_seed_file: Path = BACKEND_DIR / "samples" / "solutions.json"

    log_level: str = "INFO"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origin.split(",") if o.strip() and o.strip() != "*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
