"""Once a billable provider call is dispatched, reclaim is forbidden."""
from datetime import UTC, datetime, timedelta

import pytest

from app.little_legend.writer_queue import JobPolicy, WriterJob, claim_job


def test_expired_dispatched_job_cannot_be_reclaimed():
    now = datetime(2026, 11, 18, tzinfo=UTC)
    policy = JobPolicy(lease_seconds=30)
    job = WriterJob(
        job_id="ll_billable_dispatch_12345", story_id=1, owner_id=2,
        scene_id="scene_1", expected_revision=0, estimated_cost_usd=0.05,
    )
    running = claim_job(
        job, token="unique-token-123456789", policy=policy, now=now,
    )
    dispatched = running.model_copy(update={
        "provider_dispatched_at": now + timedelta(seconds=1),
    })
    with pytest.raises(PermissionError, match="manual reconciliation"):
        claim_job(
            dispatched, token="different-token-123456789",
            policy=policy, now=now + timedelta(seconds=31),
        )


def test_unstarted_expired_job_can_be_reclaimed():
    now = datetime(2026, 11, 18, tzinfo=UTC)
    policy = JobPolicy(lease_seconds=30)
    job = WriterJob(
        job_id="ll_unstarted_job_12345", story_id=1, owner_id=2,
        scene_id="scene_1", expected_revision=0, estimated_cost_usd=0.05,
    )
    running = claim_job(
        job, token="unique-token-123456789", policy=policy, now=now,
    )
    recovered = claim_job(
        running, token="different-token-123456789",
        policy=policy, now=now + timedelta(seconds=31),
    )
    assert recovered.attempt == 2
