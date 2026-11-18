"""Bounded, owner-scoped Little Legend portfolio cost overview."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.database.session import async_session_maker
from app.little_legend.ai_cost_ledger import cost_receipts
from app.little_legend.story_cost_summary import StoryCostSummary, summarize_story_costs
from app.little_legend.writer_queue import WriterJob
from app.little_legend.writer_queue_store import writer_jobs


class PortfolioCostSummary(BaseModel):
    owner_id: int
    stories: list[StoryCostSummary]
    estimated_usd: Decimal = Field(default=Decimal("0"), ge=0)
    confirmed_usd: Decimal = Field(default=Decimal("0"), ge=0)
    unreconciled_dispatched_jobs: int = Field(default=0, ge=0)


def summarize_portfolio(
    owner_id: int, reports: list[StoryCostSummary],
) -> PortfolioCostSummary:
    if owner_id <= 0 or len({report.story_id for report in reports}) != len(reports):
        raise ValueError("Invalid owner or duplicate story")
    return PortfolioCostSummary(
        owner_id=owner_id,
        stories=reports,
        estimated_usd=sum((r.estimated_usd for r in reports), Decimal("0")),
        confirmed_usd=sum((r.confirmed_usd for r in reports), Decimal("0")),
        unreconciled_dispatched_jobs=sum(
            r.unreconciled_dispatched_jobs for r in reports
        ),
    )


async def get_portfolio_cost_summary(
    *, owner_id: int, limit: int = 100,
) -> PortfolioCostSummary:
    """Return a bounded owner-only overview; excludes manuscripts and child data."""
    if owner_id <= 0 or not 1 <= limit <= 100:
        raise ValueError("Invalid owner or portfolio limit")
    from app.little_legend.router import stories

    async with async_session_maker() as session:
        ids = (await session.execute(
            select(stories.c.id).where(stories.c.owner_id == owner_id)
            .order_by(stories.c.id.desc()).limit(limit)
        )).scalars().all()
        if not ids:
            return summarize_portfolio(owner_id, [])
        job_rows = (await session.execute(
            select(writer_jobs.c.story_id, writer_jobs.c.payload).where(
                writer_jobs.c.owner_id == owner_id,
                writer_jobs.c.story_id.in_(ids),
            )
        )).all()
        receipt_rows = (await session.execute(
            select(
                cost_receipts.c.story_id,
                cost_receipts.c.job_id,
                func.sum(cost_receipts.c.amount_usd),
            ).where(
                cost_receipts.c.owner_id == owner_id,
                cost_receipts.c.story_id.in_(ids),
            ).group_by(cost_receipts.c.story_id, cost_receipts.c.job_id)
        )).all()
    jobs: dict[int, list[WriterJob]] = {story_id: [] for story_id in ids}
    charges: dict[int, dict[str, Decimal]] = {story_id: {} for story_id in ids}
    for story_id, payload in job_rows:
        job = WriterJob.model_validate_json(payload)
        if job.owner_id != owner_id or job.story_id != story_id:
            raise ValueError("Inconsistent owner-scoped job payload")
        jobs[story_id].append(job)
    for story_id, job_id, amount in receipt_rows:
        charges[story_id][job_id] = amount
    return summarize_portfolio(owner_id, [
        summarize_story_costs(story_id, jobs[story_id], charges[story_id])
        for story_id in ids
    ])
