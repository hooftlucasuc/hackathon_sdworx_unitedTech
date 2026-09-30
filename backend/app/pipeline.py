"""Post-call payload -> caller/company/call in Firestore, with the top-5 scored solutions.

Payload parsing is lenient: a missing data-collection field becomes null, never a crash.
Nothing personal is logged: only call ids, categories and counts.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app import scoring
from app.embeddings import TASK_DOCUMENT, TASK_QUERY, Embedder
from app.models import CATEGORIES, URGENCIES, SolutionIn
from app.store import Conflict, NotFound

log = logging.getLogger(__name__)

CANDIDATES = 10
MAX_NAME = 120
MAX_PROBLEM = 2000
MAX_SUMMARY = 4000
MAX_MESSAGE = 2000
MAX_TURNS = 300
CALL_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,160}$")
EMPTY_VALUES = {"", "none", "null", "unknown", "onbekend", "n/a", "nvt", "-"}
LEGAL_FORMS = {
    "bv", "nv", "bvba", "cv", "cvba", "vof", "commv", "comm", "vzw", "srl", "sa", "sprl",
    "sc", "scrl", "asbl", "snc", "scs", "ltd", "gmbh", "sarl", "sas", "inc", "llc",
}  # fmt: skip


class PayloadError(ValueError):
    pass


# ---------- ids ----------


def _ascii_words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", folded)


def slugify(text: str, max_len: int = 80) -> str:
    return "-".join(_ascii_words(text))[:max_len].strip("-")


def _legal_form_len(words: list[str], at_end: bool) -> int:
    """Number of tokens that form a legal form at the end (or start): 'bv', or 'b', 'v' from 'B.V.'."""
    for k in (4, 3, 2, 1):
        if len(words) > k:
            part = words[-k:] if at_end else words[:k]
            if "".join(part) in LEGAL_FORMS and (k == 1 or all(len(w) <= 4 for w in part)):
                return k
    return 0


def company_id_for(name: Optional[str]) -> Optional[str]:
    """'Bakkerij Verhulst BV', 'Bakkerij Verhulst B.V.' and 'bakkerij verhulst' map to the same id:
    legal forms are dropped, also when written with dots."""
    if not name:
        return None
    words = _ascii_words(name)
    while k := _legal_form_len(words, at_end=True):
        del words[-k:]
    while k := _legal_form_len(words, at_end=False):
        del words[:k]
    slug = "-".join(words)[:80].strip("-")
    return slug or None


def caller_id_for(name: Optional[str], company_id: Optional[str]) -> Optional[str]:
    if not name:
        return None
    base = slugify(name, 60)
    if not base:
        return None
    return f"{base}--{company_id}" if company_id else base


# ---------- parsing ----------


@dataclass
class ParsedCall:
    call_id: str
    agent_id: Optional[str]
    started_at: datetime
    duration_secs: Optional[int]
    caller_name: Optional[str]
    company_name: Optional[str]
    problem: Optional[str]
    category: str
    urgency: Optional[str]
    summary: Optional[str]
    transcript: list[dict[str, Any]] = field(default_factory=list)


def _clip(value: Any, limit: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in EMPTY_VALUES:
        return None
    return text[:limit]


def _collected(results: dict[str, Any], key: str, limit: int) -> Optional[str]:
    entry = results.get(key)
    value = entry.get("value") if isinstance(entry, dict) else entry
    return _clip(value, limit)


def _category(value: Optional[str]) -> str:
    if not value:
        return "overig"
    v = slugify(value).replace("-", "")
    return v if v in CATEGORIES else "overig"


def _urgency(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower()
    return v if v in URGENCIES else None


def parse_payload(payload: dict[str, Any], now: Optional[datetime] = None) -> ParsedCall:
    if not isinstance(payload, dict):
        raise PayloadError("payload must be a JSON object")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise PayloadError("payload has no 'data' object")
    call_id = str(data.get("conversation_id") or "")
    if not CALL_ID_RE.match(call_id):
        raise PayloadError("missing or invalid data.conversation_id")

    meta = data.get("metadata") or {}
    analysis = data.get("analysis") or {}
    results = analysis.get("data_collection_results") or {}
    if not isinstance(results, dict):
        results = {}

    start = meta.get("start_time_unix_secs")
    try:
        started_at = datetime.fromtimestamp(int(start), tz=timezone.utc) if start else None
    except (TypeError, ValueError, OverflowError):
        started_at = None
    duration = meta.get("call_duration_secs")
    try:
        duration_secs = int(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_secs = None

    transcript = []
    for turn in (data.get("transcript") or [])[:MAX_TURNS]:
        if not isinstance(turn, dict):
            continue
        message = _clip(turn.get("message"), MAX_MESSAGE)
        if not message:
            continue
        t = turn.get("time_in_call_secs")
        transcript.append(
            {
                "role": str(turn.get("role") or "unknown")[:16],
                "message": message,
                "time_in_call_secs": float(t) if isinstance(t, (int, float)) else None,
            }
        )

    return ParsedCall(
        call_id=call_id,
        agent_id=_clip(data.get("agent_id"), 160),
        started_at=started_at or now or datetime.now(timezone.utc),
        duration_secs=duration_secs,
        caller_name=_collected(results, "caller_name", MAX_NAME),
        company_name=_collected(results, "company_name", MAX_NAME),
        problem=_collected(results, "problem", MAX_PROBLEM),
        category=_category(_collected(results, "category", 40)),
        urgency=_urgency(_collected(results, "urgency", 20)),
        summary=_clip(analysis.get("transcript_summary"), MAX_SUMMARY),
        transcript=transcript,
    )


# ---------- suggestions ----------


def suggest(store, vector: list[float], now: datetime) -> list[dict[str, Any]]:
    return scoring.rank(store.nearest_solutions(vector, CANDIDATES), now)


def needs_escalation(suggestions: list[dict[str, Any]], threshold: int) -> bool:
    """No strong match in the knowledge base: the dashboard shows 'geen sterke match, escaleer'."""
    return not suggestions or suggestions[0]["score"] < threshold


def process_call(
    store,
    embedder: Embedder,
    payload: dict[str, Any],
    now: Optional[datetime] = None,
    threshold: int = 60,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    parsed = parse_payload(payload, now)

    existing = store.get_call(parsed.call_id)
    if existing is not None:
        log.info("call %s already stored; ignoring duplicate delivery", parsed.call_id)
        return {"call_id": parsed.call_id, "created": False, "suggestions": len(existing.get("suggestions") or [])}

    company_id = company_id_for(parsed.company_name)
    caller_id = caller_id_for(parsed.caller_name, company_id)

    text = parsed.problem or parsed.summary
    vector: Optional[list[float]] = None
    suggestions: list[dict[str, Any]] = []
    status = "no_problem"
    if text:
        try:
            vector = embedder.embed([text], TASK_QUERY)[0]
            status = "ok"
        except Exception:  # noqa: BLE001 - store the call anyway; the dashboard shows the status
            log.exception("embedding failed for call %s", parsed.call_id)
            status = "embedding_error"
    if vector is not None:
        try:
            suggestions = suggest(store, vector, now)
        except Exception:  # noqa: BLE001 - usually a missing or still-building vector index
            log.exception("solution search failed for call %s", parsed.call_id)
            status = "search_error"

    call_doc = {
        "call_id": parsed.call_id,
        "agent_id": parsed.agent_id,
        "caller_id": caller_id,
        "company_id": company_id,
        "caller_name": parsed.caller_name,
        "company_name": parsed.company_name,
        "started_at": parsed.started_at,
        "duration_secs": parsed.duration_secs,
        "problem": parsed.problem,
        "category": parsed.category,
        "urgency": parsed.urgency,
        "summary": parsed.summary,
        "transcript": parsed.transcript,
        "status": "open",
        "problem_embedding": vector,
        "suggestions": suggestions,
        "suggestions_status": status,
        "best_score": suggestions[0]["score"] if suggestions else None,
        "escalate": needs_escalation(suggestions, threshold),
        "chosen_solution_id": None,
        "solution_worked": None,
        "resolved_at": None,
        "received_at": now,
    }
    company = {"company_id": company_id, "name": parsed.company_name} if company_id else None
    caller = {"caller_id": caller_id, "name": parsed.caller_name, "company_id": company_id} if caller_id else None

    created = store.create_call(call_doc, company, caller)
    log.info(
        "call %s stored=%s category=%s suggestions=%d best=%s status=%s",
        parsed.call_id, created, parsed.category, len(suggestions), call_doc["best_score"], status,
    )  # fmt: skip
    return {"call_id": parsed.call_id, "created": created, "suggestions": len(suggestions)}


def rescore_call(store, call_id: str, now: Optional[datetime] = None, threshold: int = 60) -> list[dict[str, Any]]:
    """Recompute suggestions for a stored call (e.g. after new solutions were seeded)."""
    now = now or datetime.now(timezone.utc)
    vector = store.get_call_embedding(call_id)
    if vector is None:
        raise LookupError(f"call {call_id} not found or has no embedding")
    suggestions = suggest(store, vector, now)
    store.update_suggestions(call_id, suggestions, "ok", needs_escalation(suggestions, threshold))
    return suggestions


def load_calls(store, embedder: Embedder, rows: list[dict[str, Any]], threshold: int = 60) -> dict[str, int]:
    """Historical calls for the seed. Each row is an ElevenLabs post-call payload, optionally with
    "resolution": {"solution_id": ..., "worked": true|false, "resolved_at": ISO}. A resolution increments
    the solution's times_used/times_successful, so do not count those calls in the solution rows as well.
    Going through process_call guarantees the same caller/company ids and embeddings as live calls.
    """
    stats = {"created": 0, "skipped": 0, "resolved": 0}
    for row in rows:
        resolution = row.get("resolution") if isinstance(row, dict) else None
        result = process_call(store, embedder, row, threshold=threshold)
        if not result["created"]:
            stats["skipped"] += 1
            continue
        stats["created"] += 1
        if isinstance(resolution, dict) and resolution.get("solution_id"):
            when = resolution.get("resolved_at")
            resolved_at = datetime.fromisoformat(str(when).replace("Z", "+00:00")) if when else datetime.now(timezone.utc)
            try:
                store.resolve_call(
                    result["call_id"], str(resolution["solution_id"]), bool(resolution.get("worked", True)), resolved_at
                )
                stats["resolved"] += 1
            except (NotFound, Conflict) as exc:
                log.warning("call %s stored but not resolved: %s", result["call_id"], exc)
    return stats


# ---------- knowledge base ----------


def load_solutions(store, embedder: Embedder, rows: list[dict[str, Any]]) -> int:
    """Validate, embed (RETRIEVAL_DOCUMENT) and upsert solutions. Returns the number written."""
    n = 0
    for row in rows:
        sol = SolutionIn.model_validate(row)
        solution_id = sol.solution_id or slugify(sol.title)
        last_used = sol.last_used_at
        if last_used is not None and last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=timezone.utc)
        doc = sol.model_dump()
        doc.update(
            {
                "solution_id": solution_id,
                "category": _category(sol.category),
                "times_successful": min(sol.times_successful, sol.times_used),
                "last_used_at": last_used,
                "problem_embedding": embedder.embed([sol.problem_text], TASK_DOCUMENT)[0],
            }
        )
        store.upsert_solution(doc)
        n += 1
    return n
