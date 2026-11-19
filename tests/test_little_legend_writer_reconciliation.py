"""Dispatched jobs are surfaced for operator reconciliation."""
from datetime import UTC, datetime, timedelta

from app.little_legend.writer_queue import JobPolicy, WriterJob, claim_job, finish_job
from app.little_legend.writer_reconciliation import classify_reconciliation

NOW = datetime(2026, 11, 18, tzinfo=UTC)


def job():
    queued = WriterJob(
        job_id="ll_reconcile_job_12345", story_id=1, owner_id=2,
        scene_id="scene_1", expected_revision=0, estimated_cost_usd=0.05,
    )
    return claim_job(
        queued, token="unique-lease-token-12345",
        policy=JobPolicy(lease_seconds=30), now=NOW,
    )


def test_expired_dispatched_job_needs_reconciliation():
    dispatched = job().model_copy(update={"provider_dispatched_at": NOW})
    item = classify_reconciliation(
        dispatched, now=NOW + timedelta(seconds=301),
    )
    assert item is not None
    assert item.reason == "dispatched_lease_expired"
    assert item.estimated_cost_usd == 0.05


def test_active_job_not_reported():
    dispatched = job().model_copy(update={"provider_dispatched_at": NOW})
    assert classify_reconciliation(dispatched, now=NOW) is None


def test_failed_dispatched_job_needs_reconciliation():
    dispatched = job().model_copy(update={"provider_dispatched_at": NOW})
    failed = finish_job(
        dispatched, token="unique-lease-token-12345",
        success=False, retryable=False, policy=JobPolicy(), now=NOW,
    )
    assert classify_reconciliation(failed, now=NOW).reason == "provider_reconciliation_required"


def test_unstarted_failed_job_not_reported():
    failed = finish_job(
        job(), token="unique-lease-token-12345",
        success=False, retryable=False, policy=JobPolicy(), now=NOW,
    )
    assert classify_reconciliation(failed, now=NOW) is None
