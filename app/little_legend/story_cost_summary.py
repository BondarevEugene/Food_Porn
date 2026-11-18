"""Owner-scoped Little Legend AI cost reporting without estimated/actual conflation."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.database.session import async_session_maker
from app.little_legend.ai_cost_ledger import cost_receipts
from app.little_legend.writer_queue import WriterJob
from app.little_legend.writer_queue_store import writer_jobs


class ChapterCostSummary(BaseModel):
    scene_id: str
    estimated_usd: Decimal = Field(default=Decimal("0"), ge=0)
    confirmed_usd: Decimal = Field(default=Decimal("0"), ge=0)
    jobs: int = Field(default=0, ge=0)
    dispatched_jobs: int = Field(default=0, ge=0)
    unreconciled_dispatched_jobs: int = Field(default=0, ge=0)


class StoryCostSummary(BaseModel):
    story_id: int
    estimated_usd: Decimal = Field(default=Decimal("0"), ge=0)
    confirmed_usd: Decimal = Field(default=Decimal("0"), ge=0)
    jobs: int = Field(default=0, ge=0)
    dispatched_jobs: int = Field(default=0, ge=0)
    unreconciled_dispatched_jobs: int = Field(default=0, ge=0)
    chapters: list[ChapterCostSummary]


def summarize_story_costs(
    story_id: int, jobs: list[WriterJob], charges: dict[str, Decimal],
) -> StoryCostSummary:
    """Pure aggregation. Unknown provider costs remain unknown, not zero."""
    chapters: dict[str, ChapterCostSummary] = {}
    for job in jobs:
        if job.story_id != story_id:
            raise ValueError("Mixed story jobs")
        chapter = chapters.setdefault(
            job.scene_id, ChapterCostSummary(scene_id=job.scene_id)
        )
        chapter.jobs += 1
        chapter.estimated_usd += Decimal(str(job.estimated_cost_usd))
        chapter.confirmed_usd += charges.get(job.job_id, Decimal("0"))
        chapter.dispatched_jobs += int(job.provider_dispatched_at is not None)
        chapter.unreconciled_dispatched_jobs += int(
            job.provider_dispatched_at is not None and job.job_id not in charges
        )
    return StoryCostSummary(
        story_id=story_id,
        estimated_usd=sum((c.estimated_usd for c in chapters.values()), Decimal("0")),
        confirmed_usd=sum((c.confirmed_usd for c in chapters.values()), Decimal("0")),
        jobs=len(jobs),
        dispatched_jobs=sum(c.dispatched_jobs for c in chapters.values()),
        unreconciled_dispatched_jobs=sum(
            c.unreconciled_dispatched_jobs for c in chapters.values()
        ),
        chapters=list(chapters.values()),
    )


async def get_story_cost_summary(*, owner_id: int, story_id: int) -> StoryCostSummary:
    """Internal report: scope all rows to owner and story, no manuscript text."""
    if owner_id <= 0 or story_id <= 0:
        raise ValueError("Invalid owner or story")
    async with async_session_maker() as session:
        raw_jobs = (await session.execute(
            select(writer_jobs.c.payload).where(
                writer_jobs.c.owner_id == owner_id,
                writer_jobs.c.story_id == story_id,
            )
        )).scalars().all()
        cost_rows = (await session.execute(
            select(cost_receipts.c.job_id, func.sum(cost_receipts.c.amount_usd))
            .where(
                cost_receipts.c.owner_id == owner_id,
                cost_receipts.c.story_id == story_id,
            ).group_by(cost_receipts.c.job_id)
        )).all()
    jobs = [WriterJob.model_validate_json(raw) for raw in raw_jobs]
    return summarize_story_costs(
        story_id, jobs, {job_id: amount for job_id, amount in cost_rows}
    )
