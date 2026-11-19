"""Transactional PostgreSQL queue storage for Little Legend writer jobs.

The store is inert until a trusted worker explicitly invokes it.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
    select,
    update,
)

from app.database.session import async_session_maker
from app.little_legend.writer_queue import (
    JobPolicy,
    JobStatus,
    WriterJob,
    cancel_job,
    claim_job,
    finish_job,
)

queue_metadata = MetaData()
writer_jobs = Table(
    "little_legend_writer_jobs",
    queue_metadata,
    Column("job_id", String(120), primary_key=True),
    Column("story_id", Integer, nullable=False, index=True),
    Column("owner_id", BigInteger, nullable=False, index=True),
    Column("status", String(20), nullable=False, index=True),
    Column("payload", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


async def enqueue_writer_job(job: WriterJob) -> WriterJob:
    if job.status != JobStatus.QUEUED or job.attempt:
        raise ValueError("Only fresh queued jobs may be submitted")
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        # Validate ownership before persisting any job.
        from app.little_legend.router import stories

        owner = (await session.execute(
            select(stories.c.id).where(
                stories.c.id == job.story_id,
                stories.c.owner_id == job.owner_id,
            )
        )).scalar_one_or_none()
        if owner is None:
            raise ValueError("Story does not belong to job owner")
        await session.execute(insert(writer_jobs).values(
            job_id=job.job_id,
            story_id=job.story_id,
            owner_id=job.owner_id,
            status=job.status.value,
            payload=job.model_dump_json(),
            created_at=now,
            updated_at=now,
        ))
        await session.commit()
    return job


async def claim_next_writer_job(policy: JobPolicy) -> WriterJob | None:
    """Claim one job using SKIP LOCKED for multi-worker concurrency."""
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(writer_jobs)
            .where(writer_jobs.c.status.in_([
                JobStatus.QUEUED.value,
                JobStatus.RETRY_WAIT.value,
                JobStatus.RUNNING.value,
            ]))
            .order_by(writer_jobs.c.created_at)
            .with_for_update(skip_locked=True)
            .limit(50)
        )).mappings().all()
        for row in rows:
            job = WriterJob.model_validate_json(row["payload"])
            try:
                claimed = claim_job(
                    job, token=secrets.token_urlsafe(32),
                    policy=policy, now=now,
                )
            except (ValueError, PermissionError):
                continue
            await session.execute(update(writer_jobs).where(
                writer_jobs.c.job_id == job.job_id,
            ).values(
                status=claimed.status.value,
                payload=claimed.model_dump_json(),
                updated_at=now,
            ))
            await session.commit()
            return claimed
        await session.commit()
    return None


async def mark_writer_provider_dispatched(
    *, job_id: str, owner_id: int, token: str,
) -> WriterJob:
    """Persist irreversible dispatch marker before making a billable call."""
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        raw = (await session.execute(select(writer_jobs.c.payload).where(
            writer_jobs.c.job_id == job_id,
            writer_jobs.c.owner_id == owner_id,
        ).with_for_update())).scalar_one_or_none()
        if raw is None:
            raise ValueError("Writer job not found")
        job = WriterJob.model_validate_json(raw)
        if job.status != JobStatus.RUNNING or job.lease_token != token:
            raise PermissionError("Worker does not own this job")
        if job.lease_expires_at is None or job.lease_expires_at <= now:
            raise PermissionError("Lease expired before dispatch")
        if job.provider_dispatched_at is not None:
            raise PermissionError("Provider dispatch already recorded")
        from app.little_legend.production_effect_ledger import EffectKind
        from app.little_legend.worker_ai_fence import fence_worker_ai_effect

        await fence_worker_ai_effect(
            session, job=job, kind=EffectKind.WRITER_AI,
        )
        job = job.model_copy(update={"provider_dispatched_at": now})
        await session.execute(update(writer_jobs).where(
            writer_jobs.c.job_id == job_id,
        ).values(payload=job.model_dump_json(), updated_at=now))
        await session.commit()
    return job


async def transition_writer_job(
    *, job_id: str, owner_id: int, token: str,
    success: bool, policy: JobPolicy, retryable: bool = True,
    error_code: str = "provider_error",
) -> WriterJob:
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        row = (await session.execute(
            select(writer_jobs.c.payload).where(
                writer_jobs.c.job_id == job_id,
                writer_jobs.c.owner_id == owner_id,
            ).with_for_update()
        )).scalar_one_or_none()
        if row is None:
            raise ValueError("Job not found")
        changed = finish_job(
            WriterJob.model_validate_json(row),
            token=token, success=success, policy=policy,
            retryable=retryable, error_code=error_code, now=now,
        )
        await session.execute(update(writer_jobs).where(
            writer_jobs.c.job_id == job_id,
            writer_jobs.c.owner_id == owner_id,
        ).values(
            status=changed.status.value,
            payload=changed.model_dump_json(),
            updated_at=now,
        ))
        await session.commit()
    return changed


async def cancel_queued_writer_job(
    *, job_id: str, owner_id: int,
) -> WriterJob:
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        row = (await session.execute(
            select(writer_jobs.c.payload).where(
                writer_jobs.c.job_id == job_id,
                writer_jobs.c.owner_id == owner_id,
            ).with_for_update()
        )).scalar_one_or_none()
        if row is None:
            raise ValueError("Job not found")
        changed = cancel_job(WriterJob.model_validate_json(row))
        await session.execute(update(writer_jobs).where(
            writer_jobs.c.job_id == job_id,
            writer_jobs.c.owner_id == owner_id,
        ).values(
            status=changed.status.value,
            payload=changed.model_dump_json(),
            updated_at=now,
        ))
        await session.commit()
    return changed
