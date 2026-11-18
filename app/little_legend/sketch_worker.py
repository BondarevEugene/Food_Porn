"""Single-job Little Legend writer executor, with provider injected by operator.

The module never creates an AI client or starts a background loop itself.
"""
from __future__ import annotations

from typing import Protocol

from sqlalchemy import select

from app.database.session import async_session_maker
from app.little_legend.hero_contract import contract_from_blueprint
from app.little_legend.sketch_writer_briefs import (
    SketchWritingSettings,
    compose_sketch_chapter_briefs,
)
from app.little_legend.text_ai_disclosure import (
    configured_text_ai_disclosure,
    consent_allows_provider,
)
from app.little_legend.writer_checkpoints import WriterCheckpoint
from app.little_legend.writer_queue import JobPolicy, WriterJob
from app.little_legend.writer_queue_store import (
    claim_next_writer_job,
    transition_writer_job,
)
from app.little_legend.writer_result_commit import commit_writer_result


class ChapterProvider(Protocol):
    async def write_chapter(self, brief: dict) -> str: ...


def prepare_claimed_chapter(job: WriterJob, draft: object) -> dict:
    """Fail closed when any approval or source is absent or outdated."""
    if not consent_allows_provider(
        draft.text_ai_consent, configured_text_ai_disclosure()
    ):
        raise PermissionError("External AI consent missing or withdrawn")
    if not draft.outline_approved:
        raise PermissionError("Parent outline approval missing")
    if draft.parent_sketch is None or draft.graph is None or draft.blueprint is None:
        raise ValueError("Parent source or story profile missing")
    contract = contract_from_blueprint(draft.blueprint, draft.hero)
    briefs = compose_sketch_chapter_briefs(
        sketch=draft.parent_sketch, graph=draft.graph,
        contract=contract, blueprint=draft.blueprint, design=draft.design,
        settings=SketchWritingSettings(), outline_approved=True,
        existing=draft.manuscript,
    )
    selected = next((brief for brief in briefs if brief["scene_id"] == job.scene_id), None)
    if selected is None:
        raise PermissionError("Scene was approved or removed")
    existing = next(
        (chapter for chapter in draft.manuscript.chapters
         if chapter.scene_id == job.scene_id), None,
    ) if draft.manuscript is not None else None
    if (existing.revision if existing else 0) != job.expected_revision:
        raise ValueError("Queued chapter revision is stale")
    return selected


async def run_one_writer_job(
    provider: ChapterProvider, *, policy: JobPolicy | None = None,
) -> dict:
    """Claim, preflight, write and atomically commit one chapter.

    Operational errors are sanitized in the queue; never store source text or
    provider error messages there.
    """
    from app.little_legend.router import StoryDraft, stories

    policy = policy or JobPolicy()
    job = await claim_next_writer_job(policy)
    if job is None:
        return {"status": "idle"}
    if job.lease_token is None:
        raise RuntimeError("Claimed job has no lease")
    try:
        async with async_session_maker() as session:
            raw = (await session.execute(select(stories.c.data).where(
                stories.c.id == job.story_id,
                stories.c.owner_id == job.owner_id,
            ))).scalar_one_or_none()
        if raw is None:
            raise PermissionError("Story no longer exists")
        draft = StoryDraft.model_validate_json(raw)
        brief = prepare_claimed_chapter(job, draft)
    except (ValueError, PermissionError):
        await transition_writer_job(
            job_id=job.job_id, owner_id=job.owner_id,
            token=job.lease_token, success=False,
            policy=policy, retryable=False, error_code="preflight_rejected",
        )
        return {"status": "rejected", "job_id": job.job_id}
    # Once an external request is dispatched, a timeout or transport failure
    # cannot prove the provider did not bill for it. Never auto-retry it.
    try:
        text = await provider.write_chapter(brief)
    except Exception:
        try:
            await transition_writer_job(
                job_id=job.job_id, owner_id=job.owner_id,
                token=job.lease_token, success=False,
                policy=policy, retryable=False,
                error_code="provider_outcome_unknown",
            )
        except (ValueError, PermissionError):
            return {"status": "lease_lost", "job_id": job.job_id}
        return {"status": "manual_review", "job_id": job.job_id}

    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
        try:
            await transition_writer_job(
                job_id=job.job_id, owner_id=job.owner_id,
                token=job.lease_token, success=False,
                policy=policy, retryable=False,
                error_code="invalid_provider_output",
            )
        except (ValueError, PermissionError):
            return {"status": "lease_lost", "job_id": job.job_id}
        return {"status": "manual_review", "job_id": job.job_id}

    try:
        receipt = await commit_writer_result(
            story_id=job.story_id, owner_id=job.owner_id,
            token=job.lease_token,
            checkpoint=WriterCheckpoint(
                job_id=job.job_id, scene_id=job.scene_id,
                expected_revision=job.expected_revision, text=text.strip(),
            ),
            policy=policy,
        )
        return {"status": "completed", **receipt}
    except Exception:
        # Provider already returned a potentially billable result. A commit
        # error must not trigger another AI request automatically.
        try:
            await transition_writer_job(
                job_id=job.job_id, owner_id=job.owner_id,
                token=job.lease_token, success=False,
                policy=policy, retryable=False,
                error_code="commit_needs_reconciliation",
            )
        except (ValueError, PermissionError):
            return {"status": "lease_lost", "job_id": job.job_id}
        return {"status": "manual_review", "job_id": job.job_id}
