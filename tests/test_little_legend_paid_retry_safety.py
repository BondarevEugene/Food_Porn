"""Paid AI calls must never be retried after their dispatch fence."""
from datetime import UTC, datetime, timedelta

import pytest

from app.little_legend.writer_queue import (
    JobPolicy,
    JobStatus,
    WriterJob,
    claim_job,
    finish_job,
)

NOW = datetime(2026, 11, 19, tzinfo=UTC)
TOKEN = "strong-unique-worker-token-123"


def _running(*, dispatched: bool) -> WriterJob:
    job = WriterJob(
        job_id="writer-job-paid-123",
        story_id=10,
        owner_id=20,
        scene_id="scene_1",
        expected_revision=1,
        estimated_cost_usd=0.05,
    )
    running = claim_job(job, token=TOKEN, policy=JobPolicy(), now=NOW)
    if dispatched:
        running = running.model_copy(update={
            "provider_dispatched_at": NOW,
        })
    return running


@pytest.mark.parametrize("retryable", [True, False])
def test_failed_paid_dispatch_requires_reconciliation(retryable: bool) -> None:
    finished = finish_job(
        _running(dispatched=True),
        token=TOKEN,
        success=False,
        policy=JobPolicy(max_attempts=3),
        retryable=retryable,
        now=NOW + timedelta(seconds=1),
    )
    assert finished.status == JobStatus.FAILED
    assert finished.retry_after is None
    assert finished.error_code == "provider_reconciliation_required"
    assert finished.provider_dispatched_at == NOW
    with pytest.raises(PermissionError, match="manual reconciliation"):
        claim_job(
            finished, token="another-unique-worker-token",
            policy=JobPolicy(), now=NOW + timedelta(seconds=2),
        )


def test_failed_request_before_dispatch_can_retry() -> None:
    finished = finish_job(
        _running(dispatched=False),
        token=TOKEN,
        success=False,
        policy=JobPolicy(max_attempts=3),
        now=NOW + timedelta(seconds=1),
    )
    assert finished.status == JobStatus.RETRY_WAIT
    assert finished.retry_after is not None


def test_successful_paid_request_completes() -> None:
    finished = finish_job(
        _running(dispatched=True),
        token=TOKEN,
        success=True,
        policy=JobPolicy(),
        now=NOW + timedelta(seconds=1),
    )
    assert finished.status == JobStatus.COMPLETED
    assert finished.provider_dispatched_at == NOW
