"""API and TrustCard pydantic schemas. Every free-text field has a max_length."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

OWNER_STATUSES = ("active", "left", "unknown")
ITEM_STATUSES = ("active", "superseded", "draft")
ROLES = ("consultant", "expert")


# ---------- auth ----------


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    user_id: str
    username: str
    name: str
    role: str
    country: str
    expertise_tags: list[str] = []


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- countries ----------


class CountryOut(BaseModel):
    code: str
    name: str
    languages: list[str]


# ---------- Claude judgement (tool schema) ----------


class Citation(BaseModel):
    claim: str = Field(max_length=2000)
    chunk_ids: list[str] = Field(default_factory=list)


class Conflict(BaseModel):
    chunk_a: str
    chunk_b: str
    what_differs: str = Field(max_length=1000, description='e.g. "holiday pay rate: 15.34% vs 13.07%"')
    likely_current: Optional[str] = Field(default=None, description="chunk id, or null if undecidable")
    why: str = Field(max_length=1000)


class ConsistencyJudgement(BaseModel):
    answer: str = Field(max_length=8000)
    citations: list[Citation] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


# ---------- Trust Card ----------


class TrustSignal(BaseModel):
    name: str
    score: int = Field(ge=0, le=20)
    reason: str


class SourceRef(BaseModel):
    item_id: str
    title: str
    source_type: str
    country: str
    owner: Optional[str] = None
    owner_status: str = "unknown"
    updated_at: Optional[date] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    status: str = "active"
    superseded_by: Optional[str] = None  # item_id
    supersedes: Optional[str] = None  # item_id
    chunk_ids: list[str] = Field(default_factory=list)
    rank: int = 0  # 1-based retrieval rank; used as citation number in the UI
    in_scope: bool = True


class TrustCard(BaseModel):
    answer: str
    citations: list[Citation]
    conflicts: list[Conflict]
    gaps: list[str]
    trust_score: int = Field(ge=0, le=100)
    signals: list[TrustSignal]
    sources: list[SourceRef]
    suggested_expert_tags: list[str]
    escalate: bool
    country: str
    computed_at: datetime


# ---------- questions ----------


class QuestionCreate(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    country: str = Field(min_length=2, max_length=3)

    @field_validator("country")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class QuestionOut(BaseModel):
    question_id: str
    asked_by: str
    country: str
    text: str
    created_at: datetime
    status: str
    trust_card: Optional[TrustCard] = None
    assigned_expert_id: Optional[str] = None
    assigned_expert_name: Optional[str] = None
    expert_answer_item_id: Optional[str] = None
    resolved_at: Optional[datetime] = None


class QuestionSummary(BaseModel):
    question_id: str
    country: str
    text: str
    created_at: datetime
    status: str
    trust_score: Optional[int] = None
    escalate: Optional[bool] = None


class ExpertAnswerRequest(BaseModel):
    answer: str = Field(min_length=3, max_length=4000)


# ---------- sources ----------


class SourceMeta(BaseModel):
    """Sidecar metadata (`<file>.meta.yaml`) and the upload form. Country is never taken from here."""

    title: str = Field(min_length=1, max_length=300)
    source_type: str = Field(min_length=1, max_length=64)
    language: Optional[str] = Field(default=None, max_length=8)
    owner: Optional[str] = Field(default=None, max_length=120)
    owner_status: str = "unknown"
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    updated_at: Optional[date] = None
    status: str = "active"
    supersedes: Optional[str] = Field(default=None, max_length=255)
    tags: list[str] = Field(default_factory=list)

    @field_validator("owner_status")
    @classmethod
    def _owner_status(cls, v: str) -> str:
        v = (v or "unknown").lower()
        if v not in OWNER_STATUSES:
            raise ValueError(f"owner_status must be one of {OWNER_STATUSES}")
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        v = (v or "active").lower()
        if v not in ITEM_STATUSES:
            raise ValueError(f"status must be one of {ITEM_STATUSES}")
        return v

    @field_validator("owner", mode="before")
    @classmethod
    def _blank_owner(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return [str(t).strip() for t in v if str(t).strip()][:50]


class ItemOut(BaseModel):
    item_id: str
    title: str
    source_type: str
    country: str
    language: Optional[str] = None
    owner: Optional[str] = None
    owner_status: str
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    updated_at: Optional[date] = None
    status: str
    supersedes_id: Optional[str] = None
    superseded_by_id: Optional[str] = None
    tags: list[str] = []
    chunk_count: int = 0
    filename: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    preview: Optional[str] = None


class UploadResponse(BaseModel):
    item_id: str
    chunk_count: int
    superseded_item_id: Optional[str] = None
