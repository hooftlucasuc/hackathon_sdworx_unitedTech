"""Deterministic, explainable score of a solution for a call (CONTEXT.md, 'Score van een oplossing').

score        = 100 x (0.60 x similarity + 0.25 x success_rate + 0.15 x recency)
similarity   = 1 - cosine_distance(call.problem_embedding, solution.problem_embedding), clamped to [0, 1]
success_rate = (times_successful + 1) / (times_used + 2)
recency      = 1 at <= 90 days since last use, 0 at >= 730 days, linear in between; never used = 0
Category is deliberately not used as a filter: the agent's categorisation can be wrong.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

W_SIMILARITY = 0.60
W_SUCCESS = 0.25
W_RECENCY = 0.15
RECENCY_FULL_DAYS = 90
RECENCY_ZERO_DAYS = 730
TOP_K = 5


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def similarity_from_distance(cosine_distance: float) -> float:
    return _clamp01(1.0 - cosine_distance)


def success_rate(times_used: int, times_successful: int) -> float:
    used = max(0, int(times_used or 0))
    ok = min(max(0, int(times_successful or 0)), used)
    return (ok + 1) / (used + 2)


def recency(last_used_at: Optional[datetime], now: datetime) -> float:
    if last_used_at is None:
        return 0.0
    if last_used_at.tzinfo is None:
        last_used_at = last_used_at.replace(tzinfo=timezone.utc)
    days = (now - last_used_at).total_seconds() / 86400
    if days <= RECENCY_FULL_DAYS:
        return 1.0
    if days >= RECENCY_ZERO_DAYS:
        return 0.0
    return (RECENCY_ZERO_DAYS - days) / (RECENCY_ZERO_DAYS - RECENCY_FULL_DAYS)


def score(similarity: float, success: float, recent: float) -> int:
    return int(round(100 * (W_SIMILARITY * similarity + W_SUCCESS * success + W_RECENCY * recent)))


def rank(
    candidates: list[tuple[dict[str, Any], float]],
    now: datetime,
    k: int = TOP_K,
) -> list[dict[str, Any]]:
    """candidates = [(solution_doc, cosine_distance)] -> top-k suggestion dicts, best first."""
    scored = []
    for solution, distance in candidates:
        sim = similarity_from_distance(distance)
        succ = success_rate(solution.get("times_used", 0), solution.get("times_successful", 0))
        rec = recency(solution.get("last_used_at"), now)
        scored.append(
            {
                "solution_id": solution["solution_id"],
                "title": solution.get("title"),
                "score": score(sim, succ, rec),
                "reasons": {"similarity": round(sim, 3), "success": round(succ, 3), "recency": round(rec, 3)},
            }
        )
    scored.sort(key=lambda s: (s["score"], s["reasons"]["similarity"]), reverse=True)
    return scored[:k]
