"""Atomic, owner-scoped enqueue of parent-approved Little Legend chapters."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import insert, select

from app.database.session import async_session_maker
from app.little_legend.hero_contract import contract_from_blueprint
from app.little_legend.sketch_writer_briefs import (
    SketchWritingSettings,
    compose_sketch_chapter_briefs,
)
from app.little_legend.story_writer import StoryManuscript
from app.little_legend.text_ai_disclosure import (
    configured_text_ai_disclosure,
    consent_allows_provider,
)
from app.little_legend.writer_queue import JobStatus, WriterJob
from app.little_legend.writer_queue_store import writer_jobs


async def enqueue_sketch_chapters(
    *, story_id: int, owner_id: int, estimated_cost_usd: float = 0.05,
) -> list[str]:
    """Queue chapters only after server-side approval and consent checks.

    This operation does not invoke AI. Worker must independently recheck
    consent and authorization before every external provider request.
    """
    from app.little_legend.router import StoryDraft, stories

    if not 0 <= estimated_cost_usd <= 0.25:
        raise HTTPException(422, "Estimated per-chapter cost exceeds limit")
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ).with_for_update())).scalar_one_or_none()
        if raw is None:
            raise HTTPException(404, "Story not found")
        draft = StoryDraft.model_validate_json(raw)
        from app.little_legend.telegram_writer_readiness import chapter_readiness

        readiness = chapter_readiness(draft)
        if not readiness["ready"]:
            raise HTTPException(409, "; ".join(readiness["blockers"]))
        disclosure = configured_text_ai_disclosure()
        if not consent_allows_provider(draft.text_ai_consent, disclosure):
            raise HTTPException(403, "AI text processing consent is missing or outdated")
        if not draft.outline_approved:
            raise HTTPException(409, "Parent must approve the outline")
        if draft.parent_sketch is None or draft.graph is None or draft.blueprint is None:
            raise HTTPException(409, "Complete story sketch and hero profile first")
        try:
            contract = contract_from_blueprint(draft.blueprint, draft.hero)
            briefs = compose_sketch_chapter_briefs(
                sketch=draft.parent_sketch, graph=draft.graph,
                contract=contract, blueprint=draft.blueprint,
                design=draft.design, settings=SketchWritingSettings(),
                outline_approved=draft.outline_approved,
                existing=draft.manuscript,
            )
        except (ValueError, PermissionError) as exc:
            raise HTTPException(409, str(exc)) from exc
        if not briefs:
            raise HTTPException(409, "No unwritten chapters remain")
        active = (await session.execute(select(writer_jobs.c.job_id).where(
            writer_jobs.c.story_id == story_id,
            writer_jobs.c.owner_id == owner_id,
            writer_jobs.c.status.in_([
                JobStatus.QUEUED.value, JobStatus.RUNNING.value,
                JobStatus.RETRY_WAIT.value,
            ]),
        ))).scalars().all()
        if active:
            raise HTTPException(409, "Story already has pending writing jobs")
        current = draft.manuscript or StoryManuscript(hero_name=draft.hero)
        revisions = {chapter.scene_id: chapter.revision for chapter in current.chapters}
        ids = []
        for brief in briefs:
            job = WriterJob(
                job_id="ll_" + secrets.token_urlsafe(24),
                story_id=story_id, owner_id=owner_id,
                scene_id=brief["scene_id"],
                expected_revision=revisions.get(brief["scene_id"], 0),
                estimated_cost_usd=estimated_cost_usd,
            )
            await session.execute(insert(writer_jobs).values(
                job_id=job.job_id, story_id=story_id, owner_id=owner_id,
                status=job.status.value, payload=job.model_dump_json(),
                created_at=now, updated_at=now,
            ))
            ids.append(job.job_id)
        await session.commit()
    return ids
