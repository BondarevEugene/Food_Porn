"""Paid-book production conductor: advance only explicitly approved stages.

The conductor schedules existing durable writer and illustration queues.
It never calls an AI provider, grants consent, approves a manuscript, or
overrides budget and provider-dispatch fences.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from enum import StrEnum

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.database.session import async_session_maker
from app.little_legend.book_budget_store import book_budgets
from app.little_legend.fulfillment_queue import fulfillment_jobs
from app.little_legend.illustration_queue_store import (
    enqueue_illustration_jobs,
    illustration_jobs,
)
from app.little_legend.order_quotes import order_quotes
from app.little_legend.payment_entitlement import has_verified_entitlement
from app.little_legend.router import StoryDraft, stories
from app.little_legend.sketch_enqueue import enqueue_sketch_chapters
from app.little_legend.writer_queue import JobStatus
from app.little_legend.writer_queue_store import writer_jobs

logger = logging.getLogger(__name__)


class Stage(StrEnum):
    WAITING_OUTLINE = "waiting_outline"
    WAITING_TEXT_CONSENT = "waiting_text_consent"
    WRITING = "writing"
    WAITING_MANUSCRIPT = "waiting_manuscript"
    WAITING_PARENT_REVIEW = "waiting_parent_review"
    READY_TO_ILLUSTRATE = "ready_to_illustrate"
    WAITING_BUDGET = "waiting_budget"
    WAITING_IMAGE_CONSENT = "waiting_image_consent"
    ILLUSTRATING = "illustrating"
    WAITING_EDITORIAL = "waiting_editorial"
    RELEASE_QUEUE = "release_queue"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class AdvanceResult:
    quote_id: int
    stage: Stage
    enqueued: int = 0


def classify(draft: StoryDraft, *, writer_count: int, art_count: int) -> Stage:
    if draft.graph is None or draft.parent_sketch is None or not draft.outline_approved:
        return Stage.WAITING_OUTLINE
    if draft.manuscript is None or not draft.manuscript.parent_approved:
        if writer_count:
            return Stage.WRITING
        if draft.manuscript is not None and draft.manuscript.chapters:
            return Stage.WAITING_PARENT_REVIEW
        if not draft.text_ai_consent.active:
            return Stage.WAITING_TEXT_CONSENT
        return Stage.WAITING_MANUSCRIPT
    if art_count:
        return Stage.ILLUSTRATING
    if not draft.image_ai_consent.active:
        return Stage.WAITING_IMAGE_CONSENT
    return Stage.READY_TO_ILLUSTRATE


async def advance_paid_quote(
    *, quote_id: int, owner_id: int, illustration_cost_usd: float,
) -> AdvanceResult:
    """Schedule the next authorized stage; all enqueues are idempotency fenced.

    Budget is required before either stage. Consent and manuscript approval
    are rechecked transactionally inside the existing enqueue functions.
    """
    if quote_id <= 0 or owner_id <= 0:
        raise ValueError("Invalid paid quote identity")
    if not 0 < illustration_cost_usd <= 0.25:
        raise ValueError("Invalid illustration estimate")
    async with async_session_maker() as session:
        row = (await session.execute(
            select(order_quotes.c.story_id, stories.c.data)
            .join(stories, stories.c.id == order_quotes.c.story_id)
            .join(fulfillment_jobs, fulfillment_jobs.c.quote_id == order_quotes.c.id)
            .where(
                order_quotes.c.id == quote_id,
                order_quotes.c.owner_id == owner_id,
                stories.c.owner_id == owner_id,
                fulfillment_jobs.c.owner_id == owner_id,
                fulfillment_jobs.c.status == "pending",
            )
        )).one_or_none()
        if row is None:
            return AdvanceResult(quote_id, Stage.MANUAL_REVIEW)
        if not await has_verified_entitlement(
            session, quote_id=quote_id, owner_id=owner_id,
        ):
            return AdvanceResult(quote_id, Stage.MANUAL_REVIEW)
        story_id, raw = row
        draft = StoryDraft.model_validate_json(raw)
        has_budget = await session.scalar(
            select(book_budgets.c.story_id).where(
                book_budgets.c.story_id == story_id,
                book_budgets.c.owner_id == owner_id,
            )
        )
        writer_count = await session.scalar(
            select(writer_jobs.c.job_id).where(
                writer_jobs.c.story_id == story_id,
                writer_jobs.c.owner_id == owner_id,
                writer_jobs.c.status.in_((
                    JobStatus.QUEUED.value, JobStatus.RUNNING.value,
                    JobStatus.RETRY_WAIT.value,
                )),
            ).limit(1)
        )
        writer_history = await session.scalar(
            select(writer_jobs.c.job_id).where(
                writer_jobs.c.story_id == story_id,
                writer_jobs.c.owner_id == owner_id,
            ).limit(1)
        )
        art_count = await session.scalar(
            select(illustration_jobs.c.job_id).where(
                illustration_jobs.c.story_id == story_id,
                illustration_jobs.c.owner_id == owner_id,
            ).limit(1)
        )
    stage = classify(
        draft, writer_count=int(writer_count is not None),
        art_count=int(art_count is not None),
    )
    if stage == Stage.WAITING_MANUSCRIPT and writer_history is not None:
        # Completed, failed or cancelled jobs must never be regenerated
        # automatically. A parent or operator must inspect their results.
        return AdvanceResult(quote_id, Stage.WAITING_PARENT_REVIEW)
    if stage in {
        Stage.WAITING_OUTLINE, Stage.WRITING, Stage.ILLUSTRATING,
        Stage.WAITING_PARENT_REVIEW,
    }:
        return AdvanceResult(quote_id, stage)
    if stage == Stage.WAITING_EDITORIAL:
        return AdvanceResult(quote_id, Stage.RELEASE_QUEUE)
    if stage in {Stage.WAITING_TEXT_CONSENT, Stage.WAITING_IMAGE_CONSENT}:
        return AdvanceResult(quote_id, stage)
    if has_budget is None:
        return AdvanceResult(quote_id, Stage.WAITING_BUDGET)
    if stage == Stage.WAITING_MANUSCRIPT:
        try:
            ids = await enqueue_sketch_chapters(
                story_id=story_id, owner_id=owner_id,
            )
        except (HTTPException, ValueError, PermissionError) as exc:
            logger.info("Writer stage not schedulable for quote %s: %s", quote_id, type(exc).__name__)
            return AdvanceResult(quote_id, Stage.WAITING_MANUSCRIPT)
        return AdvanceResult(quote_id, Stage.WRITING, len(ids))
    if stage != Stage.READY_TO_ILLUSTRATE:
        return AdvanceResult(quote_id, stage)
    # The manuscript is parent-approved and image consent is active.
    try:
        ids = await enqueue_illustration_jobs(
            story_id=story_id, owner_id=owner_id,
            scene_ids=[node.id for node in draft.graph.nodes],
            estimated_cost_usd=illustration_cost_usd,
        )
    except (ValueError, PermissionError) as exc:
        logger.info("Art stage not schedulable for quote %s: %s", quote_id, type(exc).__name__)
        return AdvanceResult(quote_id, Stage.WAITING_EDITORIAL)
    return AdvanceResult(quote_id, Stage.ILLUSTRATING, len(ids))


async def scan_paid_queue(
    *, illustration_cost_usd: float, batch_size: int = 100,
) -> list[AdvanceResult]:
    """Scan every pending paid order in stable pages, not just the oldest 100.

    Each page is read independently, so a slow or invalid order cannot starve
    newer paid customers. The cursor uses the unique quote ID tie-breaker.
    """
    if not 1 <= batch_size <= 500:
        raise ValueError("Invalid scan batch size")
    cursor = None
    results: list[AdvanceResult] = []
    while True:
        async with async_session_maker() as session:
            query = (
                select(
                    fulfillment_jobs.c.quote_id,
                    fulfillment_jobs.c.owner_id,
                    fulfillment_jobs.c.created_at,
                )
                .where(fulfillment_jobs.c.status == "pending")
                .order_by(
                    fulfillment_jobs.c.created_at,
                    fulfillment_jobs.c.quote_id,
                )
                .limit(batch_size)
            )
            if cursor is not None:
                created_at, quote_id = cursor
                query = query.where(or_(
                    fulfillment_jobs.c.created_at > created_at,
                    (fulfillment_jobs.c.created_at == created_at)
                    & (fulfillment_jobs.c.quote_id > quote_id),
                ))
            rows = (await session.execute(query)).all()
        if not rows:
            return results
        for quote_id, owner_id, created_at in rows:
            cursor = (created_at, quote_id)
            try:
                results.append(await advance_paid_quote(
                    quote_id=quote_id, owner_id=owner_id,
                    illustration_cost_usd=illustration_cost_usd,
                ))
            except Exception:
                logger.exception("Conductor could not advance quote %s", quote_id)
                results.append(AdvanceResult(quote_id, Stage.MANUAL_REVIEW))
        if len(rows) < batch_size:
            return results


async def run(*, once: bool = False, interval: int = 15) -> None:
    if os.getenv("LL_CONDUCTOR_ENABLED") != "true":
        raise PermissionError("LL_CONDUCTOR_ENABLED=true is required")
    if not 5 <= interval <= 300:
        raise ValueError("Invalid conductor polling interval")
    price = os.environ.get("LL_ILLUSTRATION_PRICE_MICRO_USD", "")
    if not price.isdecimal() or int(price) <= 0:
        raise ValueError("Positive LL_ILLUSTRATION_PRICE_MICRO_USD is required")
    cost = int(price) / 1_000_000
    while True:
        await scan_paid_queue(illustration_cost_usd=cost)
        if once:
            return
        await asyncio.sleep(interval)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Little Legend paid production conductor")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=15)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(once=args.once, interval=args.interval))


if __name__ == "__main__":
    main()
