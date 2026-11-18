"""Lease fencing blocks stale or mismatched chapter commits."""
from datetime import UTC, datetime, timedelta

import pytest

from app.little_legend.writer_checkpoints import WriterCheckpoint
from app.little_legend.writer_queue import JobPolicy, WriterJob, claim_job
from app.little_legend.writer_result_commit import verify_checkpoint_lease

NOW = datetime(2026, 11, 18, tzinfo=UTC)
TOKEN = "unique-lease-token-123456"


def running():
    queued = WriterJob(
        job_id="writer-job-123", story_id=1, owner_id=2,
        scene_id="scene_1", expected_revision=0,
        estimated_cost_usd=0.01,
    )
    return claim_job(queued, token=TOKEN, policy=JobPolicy(), now=NOW)


def checkpoint(**changes):
    return WriterCheckpoint(**({
        "job_id": "writer-job-123", "scene_id": "scene_1",
        "expected_revision": 0, "text": "Новая глава",
    } | changes))


def test_matching_lease_permits_checkpoint():
    verify_checkpoint_lease(running(), checkpoint(), token=TOKEN, now=NOW)


def test_stale_worker_token_rejected():
    with pytest.raises(PermissionError, match="lease"):
        verify_checkpoint_lease(
            running(), checkpoint(), token="other-token", now=NOW,
        )


def test_expired_lease_rejected():
    with pytest.raises(PermissionError, match="expired"):
        verify_checkpoint_lease(
            running(), checkpoint(), token=TOKEN,
            now=NOW + timedelta(seconds=181),
        )


def test_wrong_revision_or_job_rejected():
    with pytest.raises(ValueError, match="does not match"):
        verify_checkpoint_lease(
            running(), checkpoint(expected_revision=1),
            token=TOKEN, now=NOW,
        )
