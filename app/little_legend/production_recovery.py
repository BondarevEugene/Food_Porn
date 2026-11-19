"""Conservative restart recovery planning for Little Legend production.

Plans are advisory, owner-scoped and never dispatch paid AI or Telegram calls.
"""
from __future__ import annotations

from collections import Counter
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database.session import async_session_maker
from app.little_legend.illustration_queue_store import (
    IllustrationJob,
    illustration_jobs,
)
from app.little_legend.production_checkpoint import (
    ProductionCheckpoint,
    ProductionPhase,
)
from app.little_legend.production_checkpoint_store import get_checkpoint
from app.little_legend.writer_queue import JobStatus, WriterJob


class RecoveryAction(StrEnum):
    WAIT_FOR_APPROVAL = "wait_for_approval"
    INSPECT_ILLUSTRATIONS = "inspect_illustrations"
    RESUME_UNDISPATCHED_JOBS = "resume_undispatched_jobs"
    RECONCILE_PAID_JOB = "reconcile_paid_job"
    REVIEW_FAILED_JOB = "review_failed_job"
    VERIFY_SEALED_PDF = "verify_sealed_pdf"
    RECONCILE_DELIVERY = "reconcile_delivery"
    COMPLETED = "completed"


class RecoveryPlan(BaseModel):
    owner_id: int = Field(gt=0)
    story_id: int = Field(gt=0)
    checkpoint_version: int = Field(ge=0)
    actions: list[RecoveryAction] = Field(default_factory=list)
    blocked: bool = False
    resumable_job_ids: list[str] = Field(default_factory=list)


def plan_recovery(
    *, checkpoint: ProductionCheckpoint, jobs: list[WriterJob],
) -> RecoveryPlan:
    """Identify safe work without assuming a provider request was not accepted."""
    for job in jobs:
        if job.owner_id != checkpoint.owner_id or job.story_id != checkpoint.story_id:
            raise PermissionError("Job belongs to another story or owner")
    if len({job.job_id for job in jobs}) != len(jobs):
        raise ValueError("Duplicate job IDs in recovery input")
    if checkpoint.phase == ProductionPhase.DELIVERED:
        return RecoveryPlan(
            owner_id=checkpoint.owner_id, story_id=checkpoint.story_id,
            checkpoint_version=checkpoint.version,
            actions=[RecoveryAction.COMPLETED],
        )
    if checkpoint.phase == ProductionPhase.DRAFT:
        actions = [RecoveryAction.WAIT_FOR_APPROVAL]
    elif checkpoint.phase == ProductionPhase.MANUSCRIPT_APPROVED:
        actions = [RecoveryAction.INSPECT_ILLUSTRATIONS]
    elif checkpoint.phase == ProductionPhase.ART_APPROVED:
        actions = [RecoveryAction.VERIFY_SEALED_PDF]
    elif checkpoint.phase == ProductionPhase.PDF_SEALED:
        actions = [RecoveryAction.VERIFY_SEALED_PDF]
    else:
        actions = [RecoveryAction.RECONCILE_DELIVERY]
    blocked = checkpoint.phase == ProductionPhase.DELIVERY_PENDING
    resumable: list[str] = []
    if checkpoint.phase == ProductionPhase.MANUSCRIPT_APPROVED:
        counts = Counter(job.scene_id for job in jobs)
        if any(count != 1 for count in counts.values()):
            raise ValueError("Duplicate scene jobs in recovery input")
        dispatched = [
            job for job in jobs
            if job.provider_dispatched_at is not None
            and job.status != JobStatus.COMPLETED
        ]
        failed = [
            job for job in jobs
            if job.status in {JobStatus.FAILED, JobStatus.CANCELLED}
        ]
        in_flight = [
            job for job in jobs
            if job.status == JobStatus.RUNNING
        ]
        if dispatched or in_flight:
            actions.append(RecoveryAction.RECONCILE_PAID_JOB)
            blocked = True
        if failed:
            actions.append(RecoveryAction.REVIEW_FAILED_JOB)
            blocked = True
        if not blocked:
            resumable = [
                job.job_id for job in jobs
                if job.status in {JobStatus.QUEUED, JobStatus.RETRY_WAIT}
                and job.provider_dispatched_at is None
            ]
            if resumable:
                actions.append(RecoveryAction.RESUME_UNDISPATCHED_JOBS)
    return RecoveryPlan(
        owner_id=checkpoint.owner_id, story_id=checkpoint.story_id,
        checkpoint_version=checkpoint.version,
        actions=actions, blocked=blocked, resumable_job_ids=resumable,
    )


async def plan_owned_recovery(
    *, owner_id: int, story_id: int,
) -> RecoveryPlan:
    """Read committed state; never mutate jobs or enqueue paid work."""
    checkpoint = await get_checkpoint(owner_id=owner_id, story_id=story_id)
    if checkpoint is None:
        raise PermissionError("Story checkpoint not found")
    async with async_session_maker() as session:
        rows = (await session.execute(select(illustration_jobs.c.payload).where(
            illustration_jobs.c.owner_id == owner_id,
            illustration_jobs.c.story_id == story_id,
        ))).scalars().all()
    return plan_recovery(
        checkpoint=checkpoint,
        jobs=[IllustrationJob.model_validate_json(payload) for payload in rows],
    )
