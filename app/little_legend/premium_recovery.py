"""Durable recovery of premium pre-dispatch failures.

Only failures before the irreversible provider fence may be retried.
The database row is locked and re-read to avoid races with provider dispatch.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update

from app.database.session import async_session_maker
from app.little_legend.illustration_queue_store import (
    IllustrationJob,
    illustration_jobs,
)
from app.little_legend.writer_queue import JobPolicy, JobStatus, finish_job


async def record_premium_pre_dispatch_failure(
    *, job_id: str, owner_id: int, token: str, policy: JobPolicy,
) -> IllustrationJob | None:
    """Schedule a bounded retry, or leave dispatched work for reconciliation.

    Never expose exception text: it may contain sensitive provider or child data.
    """
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        raw = (await session.execute(
            select(illustration_jobs.c.payload).where(
                illustration_jobs.c.job_id == job_id,
                illustration_jobs.c.owner_id == owner_id,
            ).with_for_update()
        )).scalar_one_or_none()
        if raw is None:
            return None
        job = IllustrationJob.model_validate_json(raw)
        if (
            not job.premium_manifest_fingerprint
            or job.status != JobStatus.RUNNING
            or job.lease_token != token
            or job.provider_dispatched_at is not None
        ):
            return None
        try:
            changed = finish_job(
                job, token=token, success=False, policy=policy,
                error_code="premium_pre_dispatch_error", retryable=True, now=now,
            )
        except PermissionError:
            # Expired lease: let the normal claim state machine reclaim it.
            return None
        await session.execute(update(illustration_jobs).where(
            illustration_jobs.c.job_id == job_id,
            illustration_jobs.c.owner_id == owner_id,
        ).values(
            status=changed.status.value,
            payload=changed.model_dump_json(),
            updated_at=now,
        ))
        await session.commit()
        return IllustrationJob.model_validate(changed)
