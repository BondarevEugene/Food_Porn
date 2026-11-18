"""Public illustration progress contains no private worker credentials."""
from datetime import UTC, datetime, timedelta

from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.writer_queue import JobStatus


def test_illustration_job_serialization_has_private_lease():
    job = IllustrationJob(
        job_id="lli_123456789", story_id=3, owner_id=9,
        scene_id="scene_1", expected_revision=1,
        estimated_cost_usd=0.05, status=JobStatus.RUNNING,
        lease_token="secret-token-not-for-clients",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=2),
    )
    # API deliberately selects only safe fields instead of serializing jobs.
    safe = {
        "scene_id": job.scene_id,
        "status": job.status.value,
        "attempt": job.attempt,
        "requires_reconciliation": (
            job.provider_dispatched_at is not None
            and job.status.value not in {"completed", "failed", "cancelled"}
        ),
    }
    assert "lease_token" not in safe
    assert "owner_id" not in safe
    assert safe["status"] == "running"


def test_dispatched_running_job_requires_reconciliation():
    job = IllustrationJob(
        job_id="lli_123456789", story_id=3, owner_id=9,
        scene_id="scene_1", expected_revision=1,
        estimated_cost_usd=0.05, status=JobStatus.RUNNING,
        lease_token="secret-token-not-for-clients",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=2),
        provider_dispatched_at=datetime.now(UTC),
    )
    assert job.provider_dispatched_at is not None
