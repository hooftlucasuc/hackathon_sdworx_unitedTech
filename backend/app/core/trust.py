"""Deterministic trust signals + aggregation. No country logic here: everything comes from CountryProfile.

Five signals, each 0-20, sum = trust_score (0-100).
freshness, ownership, scope_match, authority are computed from metadata (reproducible).
consistency is derived from the conflicts Claude named (20 - 7 per conflict, floor 0).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from app.core.countries import CountryProfile
from app.core.models import KnowledgeItem
from app.core.schemas import Conflict, ConsistencyJudgement, TrustSignal

MAX = 20
CONFLICT_PENALTY = 7
OUT_OF_DATE_PENALTY = 10


@dataclass
class TrustResult:
    trust_score: int
    signals: list[TrustSignal]
    escalate: bool
    suggested_expert_tags: list[str]
    cited_item_ids: list[str] = field(default_factory=list)


def _clamp(value: float) -> int:
    return int(max(0, min(MAX, round(value))))


def _fmt(d: Optional[date]) -> str:
    return d.isoformat() if d else "no date"


# ---------- signals ----------


def freshness_of_item(item: KnowledgeItem, profile: CountryProfile, today: date) -> float:
    """20 if age <= full_score_days; 0 if age >= zero_score_days; linear in between. No date = 0."""
    if item.updated_at is None:
        return 0.0
    age = (today - item.updated_at).days
    full, zero = profile.freshness.full_score_days, profile.freshness.zero_score_days
    if age <= full:
        return float(MAX)
    if age >= zero:
        return 0.0
    return MAX * (zero - age) / (zero - full)


def freshness(items: list[KnowledgeItem], profile: CountryProfile, today: date) -> TrustSignal:
    if not items:
        return TrustSignal(name="freshness", score=0, reason="No sources were cited.")
    n = len(items)
    weights = [n - i for i in range(n)]  # retrieval rank: first hit weighs most
    scores = [freshness_of_item(it, profile, today) for it in items]
    value = sum(w * s for w, s in zip(weights, scores)) / sum(weights)

    full = profile.freshness.full_score_days
    undated = [it for it in items if it.updated_at is None]
    dated = [it for it in items if it.updated_at is not None]
    stale = [it for it in dated if (today - it.updated_at).days > full]  # type: ignore[operator]
    if undated:
        reason = f"{len(undated)} of {n} sources have no update date; "
    else:
        reason = ""
    if stale:
        oldest = min(it.updated_at for it in stale)  # type: ignore[type-var]
        reason += f"{len(stale)} of {n} sources are older than {full} days (oldest: {_fmt(oldest)})."
    elif dated:
        newest = max(it.updated_at for it in dated)  # type: ignore[type-var]
        reason += f"All {len(dated)} sources were updated within the last {full} days (newest: {_fmt(newest)})."
    return TrustSignal(name="freshness", score=_clamp(value), reason=reason.strip())


def ownership(items: list[KnowledgeItem], profile: CountryProfile) -> TrustSignal:
    if not items:
        return TrustSignal(name="ownership", score=0, reason="No sources were cited.")
    ownerless = [it for it in items if not it.owner]
    inactive = [it for it in items if it.owner and it.owner_status != "active"]
    n = len(items)
    if ownerless and profile.require_owner:
        titles = ", ".join(f"'{it.title}'" for it in ownerless[:2])
        return TrustSignal(
            name="ownership",
            score=0,
            reason=f"{len(ownerless)} of {n} sources have no owner ({titles}); this country requires one.",
        )
    if ownerless or inactive:
        who = inactive[0] if inactive else ownerless[0]
        detail = (
            f"owner {who.owner} has status '{who.owner_status}'"
            if who.owner
            else f"'{who.title}' has no owner"
        )
        return TrustSignal(
            name="ownership",
            score=10,
            reason=f"{len(inactive) + len(ownerless)} of {n} sources lack an active owner ({detail}).",
        )
    owners = sorted({it.owner for it in items if it.owner})
    return TrustSignal(
        name="ownership",
        score=MAX,
        reason=f"All {n} sources have an active owner ({', '.join(owners)}).",
    )


def scope_match(items: list[KnowledgeItem], question_country: str, today: date) -> TrustSignal:
    if not items:
        return TrustSignal(name="scope_match", score=0, reason="No sources were cited.")
    n = len(items)
    foreign = [it for it in items if it.country not in (question_country, "ALL")]
    if foreign:
        codes = ", ".join(sorted({it.country for it in foreign}))
        return TrustSignal(
            name="scope_match",
            score=0,
            reason=f"{len(foreign)} of {n} sources belong to another country ({codes}), not {question_country}.",
        )
    out_of_date = [
        it
        for it in items
        if (it.valid_from is not None and today < it.valid_from)
        or (it.valid_to is not None and today > it.valid_to)
    ]
    if out_of_date:
        it = out_of_date[0]
        window = f"{_fmt(it.valid_from)} to {_fmt(it.valid_to) if it.valid_to else 'open'}"
        return TrustSignal(
            name="scope_match",
            score=_clamp(MAX - OUT_OF_DATE_PENALTY * len(out_of_date)),
            reason=f"{len(out_of_date)} of {n} sources are outside their validity window (e.g. '{it.title}': {window}).",
        )
    return TrustSignal(
        name="scope_match",
        score=MAX,
        reason=f"All {n} sources apply to {question_country} and are valid today ({today.isoformat()}).",
    )


def authority(items: list[KnowledgeItem], profile: CountryProfile) -> TrustSignal:
    if not items:
        return TrustSignal(name="authority", score=0, reason="No sources were cited.")
    hierarchy = profile.source_hierarchy
    ranked = sorted(items, key=lambda it: hierarchy.get(it.source_type, 0), reverse=True)
    best = ranked[0]
    level = hierarchy.get(best.source_type, 0)
    score = _clamp(MAX * level / profile.max_authority)
    if level == 0:
        reason = f"Source type '{best.source_type}' is not in the {profile.code} hierarchy."
    else:
        reason = (
            f"Best source type is '{best.source_type}' (level {level} of {profile.max_authority}"
            f" in {profile.code}): '{best.title}'."
        )
    return TrustSignal(name="authority", score=score, reason=reason)


def consistency(conflicts: list[Conflict]) -> TrustSignal:
    if not conflicts:
        return TrustSignal(name="consistency", score=MAX, reason="The cited sources agree with each other.")
    first = conflicts[0].what_differs
    more = f" and {len(conflicts) - 1} more" if len(conflicts) > 1 else ""
    return TrustSignal(
        name="consistency",
        score=_clamp(MAX - CONFLICT_PENALTY * len(conflicts)),
        reason=f"{len(conflicts)} conflict(s) between sources: {first}{more}.",
    )


# ---------- aggregation ----------


def cited_items(
    ranked_items: list[KnowledgeItem],
    judgement: ConsistencyJudgement,
    chunk_to_item: dict[str, str],
) -> list[KnowledgeItem]:
    """Items that Claude cited, in retrieval order. Falls back to every retrieved item if nothing was cited."""
    cited_ids = {chunk_to_item[c] for cit in judgement.citations for c in cit.chunk_ids if c in chunk_to_item}
    picked = [it for it in ranked_items if it.item_id in cited_ids]
    return picked or list(ranked_items)


def compute(
    ranked_items: list[KnowledgeItem],
    judgement: ConsistencyJudgement,
    profile: CountryProfile,
    question_country: str,
    today: Optional[date] = None,
    chunk_to_item: Optional[dict[str, str]] = None,
) -> TrustResult:
    today = today or date.today()
    items = cited_items(ranked_items, judgement, chunk_to_item or {})
    signals = [
        freshness(items, profile, today),
        ownership(items, profile),
        scope_match(items, question_country, today),
        authority(items, profile),
        consistency(judgement.conflicts),
    ]
    score = sum(s.score for s in signals)
    tags = sorted({t for it in items for t in it.tags} & set(profile.expert_tags))
    return TrustResult(
        trust_score=score,
        signals=signals,
        escalate=score < profile.escalation_threshold,
        suggested_expert_tags=tags,
        cited_item_ids=[it.item_id for it in items],
    )
