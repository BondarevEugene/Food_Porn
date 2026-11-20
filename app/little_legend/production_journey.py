"""Owner-scoped production journey for paid Little Legend books.

Customer-facing progress contains only stages, counters and required actions;
no child prose, photos, AI prompts, credentials or private storage keys.
"""
from __future__ import annotations

from collections import Counter
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database.session import async_session_maker
from app.little_legend.fulfillment_queue import fulfillment_jobs
from app.little_legend.illustration_queue_store import illustration_jobs
from app.little_legend.order_quotes import order_quotes
from app.little_legend.payment_entitlement import has_verified_entitlement
from app.little_legend.router import StoryDraft, stories
from app.little_legend.writer_queue import JobStatus
from app.little_legend.writer_queue_store import writer_jobs


class JourneyStage(StrEnum):
    AWAITING_PAYMENT = "awaiting_payment"
    AWAITING_OUTLINE = "awaiting_outline"
    AWAITING_TEXT_CONSENT = "awaiting_text_consent"
    WRITING = "writing"
    REVIEW_CHAPTERS = "review_chapters"
    AWAITING_IMAGE_CONSENT = "awaiting_image_consent"
    ILLUSTRATING = "illustrating"
    FINAL_REVIEW = "final_review"
    PRODUCING_PDF = "producing_pdf"
    DELIVERED = "delivered"
    MANUAL_REVIEW = "manual_review"


class JourneyView(BaseModel):
    quote_id: int
    stage: JourneyStage
    action: str
    writer_completed: int = Field(ge=0)
    writer_total: int = Field(ge=0)
    illustrations_completed: int = Field(ge=0)
    illustrations_total: int = Field(ge=0)
    payment_verified: bool
    delivered: bool


def stage_for(
    *,
    draft: StoryDraft,
    payment_verified: bool,
    fulfillment_status: str | None,
    delivery_started: bool,
    delivered: bool,
    writers: list[str],
    illustrations: list[str],
) -> tuple[JourneyStage, str]:
    """Deterministic, fail-closed transition view; never triggers paid work."""
    if delivered:
        return JourneyStage.DELIVERED, "download_book"
    if not payment_verified:
        return JourneyStage.AWAITING_PAYMENT, "complete_payment"
    if delivery_started or fulfillment_status in {"blocked", "failed"}:
        return JourneyStage.MANUAL_REVIEW, "contact_support"
    if fulfillment_status in {"processing", "ready"}:
        return JourneyStage.PRODUCING_PDF, "wait"
    if not draft.outline_approved or draft.parent_sketch is None or draft.graph is None:
        return JourneyStage.AWAITING_OUTLINE, "approve_outline"
    if not draft.manuscript or not draft.manuscript.parent_approved:
        if any(status in {JobStatus.FAILED.value, JobStatus.CANCELLED.value} for status in writers):
            return JourneyStage.MANUAL_REVIEW, "contact_support"
        if any(status in {
            JobStatus.QUEUED.value, JobStatus.RUNNING.value,
            JobStatus.RETRY_WAIT.value,
        } for status in writers):
            return JourneyStage.WRITING, "wait"
        if writers or (draft.manuscript and draft.manuscript.chapters):
            return JourneyStage.REVIEW_CHAPTERS, "approve_manuscript"
        if not draft.text_ai_consent.active:
            return JourneyStage.AWAITING_TEXT_CONSENT, "approve_text_ai"
        return JourneyStage.WRITING, "wait"
    if not illustrations:
        if not draft.image_ai_consent.active:
            return JourneyStage.AWAITING_IMAGE_CONSENT, "approve_image_ai"
        return JourneyStage.ILLUSTRATING, "wait"
    if any(status in {JobStatus.FAILED.value, JobStatus.CANCELLED.value} for status in illustrations):
        return JourneyStage.MANUAL_REVIEW, "contact_support"
    if any(status != JobStatus.COMPLETED.value for status in illustrations):
        return JourneyStage.ILLUSTRATING, "wait"
    return JourneyStage.FINAL_REVIEW, "approve_final_book"


async def inspect_paid_journey(*, quote_id: int, owner_id: int) -> JourneyView | None:
    if quote_id <= 0 or owner_id <= 0:
        return None
    async with async_session_maker() as session:
        row = (await session.execute(
            select(
                order_quotes.c.story_id, stories.c.data,
                fulfillment_jobs.c.status,
                fulfillment_jobs.c.delivery_started_at,
                fulfillment_jobs.c.delivered_at,
            )
            .join(stories, stories.c.id == order_quotes.c.story_id)
            .outerjoin(
                fulfillment_jobs,
                (fulfillment_jobs.c.quote_id == order_quotes.c.id)
                & (fulfillment_jobs.c.owner_id == owner_id),
            )
            .where(
                order_quotes.c.id == quote_id,
                order_quotes.c.owner_id == owner_id,
                stories.c.owner_id == owner_id,
            )
        )).one_or_none()
        if row is None:
            return None
        story_id, raw, status, started_at, delivered_at = row
        verified = await has_verified_entitlement(
            session, quote_id=quote_id, owner_id=owner_id,
        )
        writer_statuses = (await session.execute(
            select(writer_jobs.c.status).where(
                writer_jobs.c.story_id == story_id,
                writer_jobs.c.owner_id == owner_id,
            )
        )).scalars().all()
        illustration_statuses = (await session.execute(
            select(illustration_jobs.c.status).where(
                illustration_jobs.c.story_id == story_id,
                illustration_jobs.c.owner_id == owner_id,
            )
        )).scalars().all()
    draft = StoryDraft.model_validate_json(raw)
    writers = list(writer_statuses)
    art = list(illustration_statuses)
    stage, action = stage_for(
        draft=draft, payment_verified=verified,
        fulfillment_status=status,
        delivery_started=started_at is not None,
        delivered=delivered_at is not None and verified,
        writers=writers, illustrations=art,
    )
    writer_counts = Counter(writers)
    art_counts = Counter(art)
    return JourneyView(
        quote_id=quote_id, stage=stage, action=action,
        writer_completed=writer_counts[JobStatus.COMPLETED.value],
        writer_total=len(writers),
        illustrations_completed=art_counts[JobStatus.COMPLETED.value],
        illustrations_total=len(art),
        payment_verified=verified,
        delivered=stage == JourneyStage.DELIVERED,
    )
