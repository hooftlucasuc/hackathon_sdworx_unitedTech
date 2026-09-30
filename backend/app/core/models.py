"""Firestore document models. Plain dataclasses with to_doc/from_doc; dates stored as ISO strings."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timezone
from typing import Any, Optional


def make_item_id(country: str, relative_path: str) -> str:
    """Deterministic id so re-ingesting the same file updates in place."""
    return hashlib.sha256(f"{country}{relative_path}".encode()).hexdigest()[:16]


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def parse_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def parse_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class User:
    user_id: str
    username: str
    name: str
    role: str  # consultant | expert
    country: str
    expertise_tags: list[str] = field(default_factory=list)
    password_hash: str = ""

    def to_doc(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> User:
        return cls(**{f.name: doc.get(f.name) for f in fields(cls)})


@dataclass
class KnowledgeItem:
    item_id: str
    title: str
    source_type: str
    country: str
    language: Optional[str] = None
    owner: Optional[str] = None
    owner_status: str = "unknown"  # active | left | unknown
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    updated_at: Optional[date] = None
    status: str = "active"  # active | superseded | draft
    supersedes_id: Optional[str] = None
    superseded_by_id: Optional[str] = None
    gcs_uri: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    chunk_count: int = 0
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    filename: Optional[str] = None
    preview: str = ""  # first 2000 chars, for GET /items/{id}

    def to_doc(self) -> dict[str, Any]:
        return {k: _iso(v) for k, v in asdict(self).items()}

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> KnowledgeItem:
        data = {f.name: doc.get(f.name) for f in fields(cls)}
        for key in ("valid_from", "valid_to", "updated_at"):
            data[key] = parse_date(data[key])
        data["created_at"] = parse_datetime(data["created_at"])
        data["tags"] = list(data["tags"] or [])
        data["chunk_count"] = int(data["chunk_count"] or 0)
        data["preview"] = data["preview"] or ""
        data["owner_status"] = data["owner_status"] or "unknown"
        data["status"] = data["status"] or "active"
        return cls(**data)


@dataclass
class Chunk:
    chunk_id: str
    item_id: str
    country: str
    status: str
    seq: int
    text: str
    embedding: list[float] = field(default_factory=list)
    msg_author: Optional[str] = None
    msg_timestamp: Optional[str] = None

    def to_doc(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Chunk:
        data = {f.name: doc.get(f.name) for f in fields(cls)}
        emb = data.get("embedding")
        data["embedding"] = list(emb) if emb is not None else []
        data["seq"] = int(data["seq"] or 0)
        return cls(**data)


@dataclass
class Question:
    question_id: str
    asked_by: str
    country: str
    text: str
    created_at: datetime
    status: str = "answered"  # answered | escalated | resolved
    trust_card: Optional[dict[str, Any]] = None
    assigned_expert_id: Optional[str] = None
    expert_answer_item_id: Optional[str] = None
    resolved_at: Optional[datetime] = None

    def to_doc(self) -> dict[str, Any]:
        return {k: _iso(v) for k, v in asdict(self).items()}

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Question:
        data = {f.name: doc.get(f.name) for f in fields(cls)}
        data["created_at"] = parse_datetime(data["created_at"]) or now_utc()
        data["resolved_at"] = parse_datetime(data["resolved_at"])
        data["status"] = data["status"] or "answered"
        return cls(**data)
