"""State machine tests for writer job safety and retry budgets."""
from datetime import UTC, datetime, timedelta

import pytest

from app.little_legend.writer_queue import (
    JobPolicy,
    JobStatus,
    WriterJob,
    cancel_job,
    claim_job,
    finish_job,
)

NOW = datetime(2026, 11, 18, tzinfo=UTC)
TOKEN = "strong-unique-token-123"


def job(**overrides):
    return WriterJob(
        **({
            "job_id": "writer-job-123",
            "story_id": 10,
            "owner_id": 20,
            "scene_id": "scene_1",
            "expected_revision": 0,
            "estimated_cost_usd": 0.05,
        } | overrides)
    )


def test_claim_and_success():
    policy = JobPolicy()
    running = claim_job(job(), token=TOKEN, policy=policy, now=NOW)
    assert running.status == JobStatus.RUNNING
    assert running.attempt == 1
    done = finish_job(
        running, token=TOKEN, success=True, policy=policy,
        now=NOW + timedelta(seconds=1),
    )
    assert done.status == JobStatus.COMPLETED
    with pytest.raises(ValueError):
        claim_job(done, token="another-unique-token-456", policy=policy, now=NOW)


def test_retry_with_backoff_and_exhaustion():
    policy = JobPolicy(max_attempts=2, retry_base_seconds=10)
    running = claim_job(job(), token=TOKEN, policy=policy, now=NOW)
    waiting = finish_job(
        running, token=TOKEN, success=False, policy=policy,
        now=NOW + timedelta(seconds=1),
    )
    assert waiting.retry_after == NOW + timedelta(seconds=11)
    with pytest.raises(ValueError):
        claim_job(waiting, token="another-unique-token-456", policy=policy, now=NOW)
    running2 = claim_job(
        waiting, token="another-unique-token-456", policy=policy,
        now=NOW + timedelta(seconds=12),
    )
    failed = finish_job(
        running2, token="another-unique-token-456",
        success=False, policy=policy, now=NOW + timedelta(seconds=13),
    )
    assert failed.status == JobStatus.FAILED


def test_expired_worker_cannot_finish():
    policy = JobPolicy(lease_seconds=30)
    running = claim_job(job(), token=TOKEN, policy=policy, now=NOW)
    with pytest.raises(PermissionError):
        finish_job(
            running, token=TOKEN, success=True, policy=policy,
            now=NOW + timedelta(seconds=31),
        )
    recovered = claim_job(
        running, token="another-unique-token-456",
        policy=policy, now=NOW + timedelta(seconds=31),
    )
    assert recovered.attempt == 2


def test_cost_cap_and_cancel():
    policy = JobPolicy(max_estimated_cost_usd=0.10)
    with pytest.raises(PermissionError):
        claim_job(job(estimated_cost_usd=0.11), token=TOKEN, policy=policy, now=NOW)
    cancelled = cancel_job(job())
    with pytest.raises(ValueError):
        claim_job(cancelled, token=TOKEN, policy=policy, now=NOW)
