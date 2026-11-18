"""AI cost reporting separates expected spend and confirmed receipts."""
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.little_legend.story_cost_summary import summarize_story_costs
from app.little_legend.writer_queue import WriterJob


def make_job(scene, cost, dispatched=False):
    return WriterJob(
        job_id="job_12345678_" + scene, story_id=42, owner_id=7,
        scene_id=scene, expected_revision=0, estimated_cost_usd=cost,
        provider_dispatched_at=datetime(2026, 11, 18, tzinfo=UTC)
        if dispatched else None,
    )


def test_story_summary_does_not_count_estimates_as_confirmed():
    a = make_job("a", 0.05, True)
    b = make_job("b", 0.10)
    result = summarize_story_costs(42, [a, b], {a.job_id: Decimal("0.023456")})
    assert result.estimated_usd == Decimal("0.15")
    assert result.confirmed_usd == Decimal("0.023456")
    assert result.dispatched_jobs == 1
    assert len(result.chapters) == 2


def test_summary_rejects_mixed_story_data():
    with pytest.raises(ValueError, match="Mixed story"):
        summarize_story_costs(43, [make_job("a", 0.05)], {})


def test_dispatched_without_receipt_remains_unreconciled():
    a = make_job("a", 0.05, True)
    b = make_job("b", 0.10, True)
    report = summarize_story_costs(42, [a, b], {a.job_id: Decimal("0")})
    assert report.dispatched_jobs == 2
    assert report.unreconciled_dispatched_jobs == 1
    assert report.confirmed_usd == Decimal("0")
    assert report.chapters[0].unreconciled_dispatched_jobs == 0
    assert report.chapters[1].unreconciled_dispatched_jobs == 1


def test_undispatched_job_is_not_unreconciled():
    report = summarize_story_costs(42, [make_job("a", 0.05)], {})
    assert report.unreconciled_dispatched_jobs == 0
