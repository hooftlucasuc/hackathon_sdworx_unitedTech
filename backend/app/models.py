"""API schemas. Mirrors CONTEXT.md (contract). Incoming webhook payloads are parsed leniently in pipeline.py."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

CATEGORIES = (
    "vakantiegeld",
    "loonberekening",
    "ziekte",
    "dimona",
    "maaltijdcheques",
    "bedrijfswagen",
    "ontslag",
    "overig",
)
URGENCIES = ("laag", "midden", "hoog")
ID_PATTERN = r"^[A-Za-z0-9_\-]{1,160}$"


class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Reasons(_Out):
    similarity: float
    success: float
    recency: float


class Suggestion(_Out):
    solution_id: str
    title: Optional[str] = None
    score: int
    reasons: Reasons


class SuggestionDetail(Suggestion):
    solution_text: Optional[str] = None
    problem_text: Optional[str] = None
    category: Optional[str] = None
    times_used: int = 0
    times_successful: int = 0
    last_used_at: Optional[datetime] = None


class TranscriptTurn(_Out):
    role: str
    message: str = ""
    time_in_call_secs: Optional[float] = None


class CallSummary(_Out):
    call_id: str
    caller_id: Optional[str] = None
    company_id: Optional[str] = None
    caller_name: Optional[str] = None
    company_name: Optional[str] = None
    started_at: datetime
    duration_secs: Optional[int] = None
    problem: Optional[str] = None
    category: str = "overig"
    urgency: Optional[str] = None
    status: str = "open"
    chosen_solution_id: Optional[str] = None
    best_score: Optional[int] = None
    escalate: bool = False


class Call(CallSummary):
    summary: Optional[str] = None
    transcript: list[TranscriptTurn] = []
    suggestions: list[Suggestion] = []
    suggestions_status: str = "ok"  # ok | no_problem | embedding_error | search_error
    resolved_at: Optional[datetime] = None
    solution_worked: Optional[bool] = None


class Caller(_Out):
    caller_id: str
    name: Optional[str] = None
    company_id: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    call_count: int = 0


class CallerDetail(_Out):
    caller: Caller
    calls: list[CallSummary]


class Company(_Out):
    company_id: str
    name: Optional[str] = None
    sector: Optional[str] = None
    size: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    call_count: int = 0
    open_issues: int = 0


class CompanyDetail(_Out):
    company: Company
    calls: list[CallSummary]


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    solution_id: str = Field(min_length=1, max_length=160, pattern=ID_PATTERN)
    worked: bool


class ResolveResult(_Out):
    call_id: str
    status: str
    chosen_solution_id: str
    solution_worked: bool


class WebhookAck(_Out):
    call_id: Optional[str] = None
    created: bool = False
    suggestions: int = 0
    ignored: Optional[str] = None


class SolutionIn(BaseModel):
    """One row of a solutions file (samples/solutions.json or D's seed data)."""

    model_config = ConfigDict(extra="ignore")
    solution_id: Optional[str] = Field(default=None, max_length=160, pattern=ID_PATTERN)
    title: str = Field(min_length=1, max_length=200)
    problem_text: str = Field(min_length=1, max_length=4000)
    solution_text: str = Field(min_length=1, max_length=8000)
    category: str = "overig"
    times_used: int = Field(default=0, ge=0)
    times_successful: int = Field(default=0, ge=0)
    last_used_at: Optional[datetime] = None
    source_call_id: Optional[str] = None
