"""Read-only paid-book release readiness: same gates as the PDF worker.

Never sends messages, enqueues AI, changes approvals, or returns child content.
"""
from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database.session import async_session_maker
from app.little_legend.fulfillment_queue import fulfillment_jobs
from app.little_legend.illustration_queue_store import IllustrationJob, illustration_jobs
from app.little_legend.order_quotes import order_quotes
from app.little_legend.payment_entitlement import has_verified_entitlement
from app.little_legend.production_readiness import assess_production
from app.little_legend.router import StoryDraft, stories


class ReleaseReadiness(BaseModel):
    quote_id: int = Field(gt=0)
    payment_verified: bool
    fulfillment_status: str | None
    release_ready: bool
    completed_scenes: int = Field(ge=0)
    total_scenes: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)
    requires_manual_review: bool = False


def assess_paid_release(
    *, quote_id: int, draft: StoryDraft, payment_verified: bool,
    fulfillment_status: str | None, art_jobs: list[IllustrationJob],
) -> ReleaseReadiness:
    """Pure release assessment; do not trust counts alone or old revisions."""
    blockers: list[str] = []
    if not payment_verified:
        blockers.append("payment_not_verified")
    if fulfillment_status is None:
        blockers.append("fulfillment_not_requested")
    elif fulfillment_status in {"blocked", "failed"}:
        blockers.append("fulfillment_blocked")
    elif fulfillment_status not in {"pending", "processing", "ready", "delivered"}:
        blockers.append("fulfillment_state_unknown")
    if draft.graph is None:
        blockers.append("graph_missing")
    if draft.manuscript is None:
        blockers.append("manuscript_missing")
    decision = draft.editorial_decision
    editorial_approved = all((
        decision.hero_fidelity_reviewed,
        decision.age_appropriateness_reviewed,
        decision.narrative_continuity_reviewed,
        decision.parent_final_approval,
    ))
    if not editorial_approved:
        blockers.append("final_parent_editorial_approval_missing")
    completed = 0
    total = len(draft.graph.nodes) if draft.graph is not None else 0
    if draft.graph is not None and draft.manuscript is not None:
        report = assess_production(
            graph=draft.graph, manuscript=draft.manuscript,
            jobs=art_jobs, editorial_approved=editorial_approved,
        )
        completed = report.completed_scenes
        blockers.extend(issue.code for issue in report.issues
                        if issue.code != "pdf_not_verified")
    statuses = Counter(job.status.value for job in art_jobs)
    manual = (
        fulfillment_status in {"blocked", "failed"}
        or bool(statuses.get("failed") or statuses.get("cancelled"))
        or any(code in blockers for code in (
            "illustration_job_count_invalid",
            "illustration_revision_stale",
            "duplicate_scene_ids",
            "duplicate_chapters",
            "unexpected_illustration",
            "unexpected_chapter",
        ))
    )
    return ReleaseReadiness(
        quote_id=quote_id,
        payment_verified=payment_verified,
        fulfillment_status=fulfillment_status,
        release_ready=not blockers,
        completed_scenes=completed,
        total_scenes=total,
        blockers=sorted(set(blockers)),
        requires_manual_review=manual,
    )


async def inspect_paid_release(
    *, quote_id: int, owner_id: int,
) -> ReleaseReadiness | None:
    if quote_id <= 0 or owner_id <= 0:
        return None
    async with async_session_maker() as session:
        row = (await session.execute(
            select(
                order_quotes.c.story_id, stories.c.data,
                fulfillment_jobs.c.status,
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
        story_id, raw, status = row
        verified = await has_verified_entitlement(
            session, quote_id=quote_id, owner_id=owner_id,
        )
        payloads = (await session.execute(
            select(illustration_jobs.c.payload).where(
                illustration_jobs.c.story_id == story_id,
                illustration_jobs.c.owner_id == owner_id,
            )
        )).scalars().all()
    draft = StoryDraft.model_validate_json(raw)
    jobs = [IllustrationJob.model_validate_json(payload) for payload in payloads]
    return assess_paid_release(
        quote_id=quote_id, draft=draft, payment_verified=verified,
        fulfillment_status=status, art_jobs=jobs,
    )
