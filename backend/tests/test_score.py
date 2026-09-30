from datetime import datetime, timedelta, timezone

import pytest

from app import scoring

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def test_success_rate_laplace():
    assert scoring.success_rate(0, 0) == 0.5
    assert scoring.success_rate(10, 8) == 0.75
    assert scoring.success_rate(2, 5) == 0.75  # successes capped at uses


@pytest.mark.parametrize(
    "days,expected",
    [(0, 1.0), (90, 1.0), (410, 0.5), (730, 0.0), (2000, 0.0)],
)
def test_recency_linear(days, expected):
    assert scoring.recency(NOW - timedelta(days=days), NOW) == pytest.approx(expected)


def test_recency_never_used_is_zero():
    assert scoring.recency(None, NOW) == 0.0


def test_similarity_clamped():
    assert scoring.similarity_from_distance(0.1) == pytest.approx(0.9)
    assert scoring.similarity_from_distance(1.5) == 0.0
    assert scoring.similarity_from_distance(-0.2) == 1.0


def test_score_formula():
    assert scoring.score(1, 1, 1) == 100
    assert scoring.score(0, 0, 0) == 0
    # 100 * (0.6*0.9 + 0.25*0.75 + 0.15*0.5) = 80.25
    assert scoring.score(0.9, 0.75, 0.5) == 80


def test_rank_orders_and_truncates():
    candidates = [
        ({"solution_id": f"s{i}", "title": f"S{i}", "times_used": 10, "times_successful": 5,
          "last_used_at": NOW}, 0.05 * i)
        for i in range(8)
    ]  # fmt: skip
    ranked = scoring.rank(candidates, NOW)
    assert len(ranked) == 5
    assert [r["solution_id"] for r in ranked] == ["s0", "s1", "s2", "s3", "s4"]
    assert ranked[0]["reasons"] == {"similarity": 1.0, "success": 0.5, "recency": 1.0}
    assert all(0 <= r["score"] <= 100 for r in ranked)


def test_rank_success_can_beat_similarity():
    proven = {"solution_id": "proven", "times_used": 40, "times_successful": 40, "last_used_at": NOW}
    untested = {"solution_id": "untested", "times_used": 0, "times_successful": 0, "last_used_at": None}
    ranked = scoring.rank([(untested, 0.10), (proven, 0.15)], NOW)
    assert ranked[0]["solution_id"] == "proven"
