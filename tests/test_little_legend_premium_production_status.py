"""Customer-facing production status is safe and deterministic."""

from datetime import UTC, datetime, timedelta

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.premium_production_status import premium_production_status
from app.little_legend.writer_queue import JobStatus


def job(status: JobStatus, *, dispatched: bool = False) -> IllustrationJob:
    now = datetime.now(UTC)
    return IllustrationJob(
        job_id="lli_status_123456", owner_id=1, story_id=2,
        scene_id="premium-cover", expected_revision=1,
        estimated_cost_usd=0.05, status=status,
        premium_manifest_fingerprint="manifest",
        lease_token="long-lease-token-123" if status == JobStatus.RUNNING else None,
        lease_expires_at=now - timedelta(minutes=1)
        if status == JobStatus.RUNNING else None,
        provider_dispatched_at=now - timedelta(minutes=5) if dispatched else None,
    )


def test_empty_and_queued_batch() -> None:
    assert premium_production_status([])["state"] == "not_started"
    assert premium_production_status([job(JobStatus.QUEUED)])["state"] == "queued"


def test_complete_batch_progress() -> None:
    result = premium_production_status([job(JobStatus.COMPLETED)])
    assert result["state"] == "illustrations_complete"
    assert result["completed"] == 1
    assert result["total"] == 1
    assert not result["requires_attention"]


def test_expired_dispatched_job_requires_manual_reconciliation() -> None:
    result = premium_production_status([job(JobStatus.RUNNING, dispatched=True)])
    assert result["state"] == "reconciliation"
    assert result["requires_attention"]
    assert "lease" not in str(result)
    assert "manifest" not in str(result)


def test_failure_and_retry_are_distinct() -> None:
    assert premium_production_status([job(JobStatus.FAILED)])["state"] == (
        "attention_required"
    )
    assert premium_production_status([job(JobStatus.RETRY_WAIT)])["state"] == (
        "retry_scheduled"
    )
