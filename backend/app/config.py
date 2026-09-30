"""Settings from environment. `.env` is read from the repo root or from backend/."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gcp_project: str = ""
    gcp_region: str = "europe-west1"
    google_application_credentials: Optional[str] = None
    gcs_bucket: str = ""
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"

    jwt_secret: str = Field(default="", description="HS256 secret; required outside tests")
    jwt_expires_min: int = 480
    frontend_origin: str = "http://localhost:5173"

    seed_consultant_password: str = ""
    seed_expert_password: str = ""

    # firestore (default) or memory (tests / frontend dev without GCP). Not a product feature.
    store_backend: str = "firestore"

    countries_dir: Path = REPO_ROOT / "countries"
    sources_dir: Path = REPO_ROOT / "sources"

    max_upload_bytes: int = 10 * 1024 * 1024
    retrieval_k: int = 8

    @property
    def bucket_name(self) -> str:
        if self.gcs_bucket and "${" not in self.gcs_bucket:
            return self.gcs_bucket
        return f"{self.gcp_project}-trustcard-raw"


@lru_cache
def get_settings() -> Settings:
    return Settings()
