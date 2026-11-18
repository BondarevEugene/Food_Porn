"""Read-only operator reconciliation inventory for billable writer dispatches.

No retry, cancellation, or billing correction is performed automatically.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database.session import async_session_maker
from app.little_legend.writer_queue import JobStatus, WriterJob
from app.little_legend.writer_queue_store import writer_jobs


class ReconciliationItem(BaseModel):
    job_id: str
    story_id: int
    owner_id: int
    scene_id: str
    status: JobStatus
    attempt: int
    estimated_cost_usd: float = Field(ge=0)
    provider_dispatched_at: datetime
    reason: str


def classify_reconciliation(
    job: WriterJob, *, now: datetime, grace_seconds: int = 300,
) -> ReconciliationItem | None:
    """Flag potentially billed jobs requiring manual provider reconciliation."""
    if job.provider_dispatched_at is None:
        return None
    if job.status == JobStatus.COMPLETED:
        return None
    if job.status == JobStatus.RUNNING:
        if job.lease_expires_at is not None and job.lease_expires_at > now:
            return None
        if now < job.provider_dispatched_at + timedelta(seconds=grace_seconds):
            return None
        reason = "dispatched_lease_expired"
    elif job.status == JobStatus.FAILED:
        reason = job.error_code or "provider_outcome_unknown"
    else:
        reason = "dispatched_unresolved"
    return ReconciliationItem(
        job_id=job.job_id, story_id=job.story_id, owner_id=job.owner_id,
        scene_id=job.scene_id, status=job.status, attempt=job.attempt,
        estimated_cost_usd=job.estimated_cost_usd,
        provider_dispatched_at=job.provider_dispatched_at, reason=reason,
    )


async def list_reconciliation_items(
    *, limit: int = 100, grace_seconds: int = 300,
) -> list[ReconciliationItem]:
    """Return bounded, content-free inventory for trusted internal tooling."""
    if not 1 <= limit <= 500:
        raise ValueError("Limit must be between 1 and 500")
    if not 0 <= grace_seconds <= 86400:
        raise ValueError("Invalid reconciliation grace period")
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(writer_jobs.c.payload)
            .where(writer_jobs.c.status.in_([
                JobStatus.RUNNING.value, JobStatus.FAILED.value,
                JobStatus.RETRY_WAIT.value, JobStatus.CANCELLED.value,
            ]))
            .order_by(writer_jobs.c.created_at)
            .limit(limit)
        )).scalars().all()
    now = datetime.now(UTC)
    return [
        item
        for raw in rows
        if (item := classify_reconciliation(
            WriterJob.model_validate_json(raw),
            now=now, grace_seconds=grace_seconds,
        )) is not None
    ]
