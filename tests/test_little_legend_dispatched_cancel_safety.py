"""A dispatched paid request must remain visible for charge reconciliation."""
from datetime import UTC, datetime

import pytest

from app.little_legend.writer_queue import (
    JobStatus,
    WriterJob,
    cancel_job,
)


def _job(*, dispatched: bool) -> WriterJob:
    return WriterJob(
        job_id="writer-job-cancel-123",
        story_id=10,
        owner_id=20,
        scene_id="scene_1",
        expected_revision=0,
        estimated_cost_usd=0.05,
        provider_dispatched_at=(
            datetime(2026, 11, 19, tzinfo=UTC) if dispatched else None
        ),
    )


def test_dispatched_job_cannot_be_cancelled() -> None:
    with pytest.raises(PermissionError, match="reconciliation"):
        cancel_job(_job(dispatched=True))


def test_undispatched_job_can_be_cancelled() -> None:
    cancelled = cancel_job(_job(dispatched=False))
    assert cancelled.status == JobStatus.CANCELLED


def test_failed_dispatched_job_cannot_be_cancelled() -> None:
    failed = _job(dispatched=True).model_copy(
        update={"status": JobStatus.FAILED},
    )
    with pytest.raises(PermissionError, match="reconciliation"):
        cancel_job(failed)
