"""Premium-only queue claim and irreversible paid-provider dispatch fence.

The legacy scene worker never claims premium jobs. This module supplies a
separate, owner-scoped path for approved cover and chapter moments.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.database.session import async_session_maker
from app.little_legend.illustration_queue_store import (
    IllustrationJob,
    illustration_jobs,
)
from app.little_legend.premium_batch_manifest import PremiumBatchManifest
from app.little_legend.premium_queue_safety import require_premium_batch_ready
from app.little_legend.premium_visual_contract import BookVisualPlan
from app.little_legend.writer_queue import JobPolicy, JobStatus, claim_job


async def claim_next_premium_illustration_job(
    *, policy: JobPolicy,
) -> IllustrationJob | None:
    """Claim a premium job without ever touching legacy scene-based jobs."""
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(illustration_jobs).where(
                illustration_jobs.c.status.in_([
                    JobStatus.QUEUED.value, JobStatus.RETRY_WAIT.value,
                    JobStatus.RUNNING.value,
                ])
            ).order_by(illustration_jobs.c.created_at)
            .with_for_update(skip_locked=True).limit(50)
        )).mappings().all()
        for row in rows:
            job = IllustrationJob.model_validate_json(row["payload"])
            if not job.premium_manifest_fingerprint or not job.premium_story_fingerprint:
                continue
            try:
                claimed = claim_job(
                    job, token=secrets.token_urlsafe(32), policy=policy, now=now,
                )
            except (ValueError, PermissionError):
                continue
            await session.execute(update(illustration_jobs).where(
                illustration_jobs.c.job_id == job.job_id,
            ).values(
                status=claimed.status.value,
                payload=claimed.model_dump_json(), updated_at=now,
            ))
            await session.commit()
            return IllustrationJob.model_validate(claimed)
        await session.commit()
    return None


async def fence_premium_illustration_dispatch(
    *, job_id: str, owner_id: int, token: str,
    manifest: PremiumBatchManifest, plan: BookVisualPlan,
) -> IllustrationJob:
    """Validate current approved story and reserve cost before any AI call.

    The caller must invoke the provider only after this transaction commits.
    A dispatched job must never be automatically retried.
    """
    from app.little_legend.art_preflight import require_book_art_ready
    from app.little_legend.image_ai_consent import (
        configured_image_ai_disclosure,
        consent_allows_image_ai,
    )
    from app.little_legend.production_effect_ledger import EffectKind
    from app.little_legend.router import StoryDraft, stories
    from app.little_legend.worker_ai_fence import fence_worker_ai_effect

    now = datetime.now(UTC)
    async with async_session_maker() as session:
        raw = (await session.execute(select(illustration_jobs.c.payload).where(
            illustration_jobs.c.job_id == job_id,
            illustration_jobs.c.owner_id == owner_id,
        ).with_for_update())).scalar_one_or_none()
        if raw is None:
            raise ValueError("Premium illustration job not found")
        job = IllustrationJob.model_validate_json(raw)
        if (not job.premium_manifest_fingerprint
                or not job.premium_story_fingerprint
                or job.status != JobStatus.RUNNING
                or job.lease_token != token
                or job.lease_expires_at is None
                or job.lease_expires_at <= now
                or job.provider_dispatched_at is not None):
            raise PermissionError("Premium job is not eligible for dispatch")
        if (manifest.owner_id != owner_id or manifest.story_id != job.story_id
                or manifest.fingerprint != job.premium_manifest_fingerprint):
            raise PermissionError("Premium manifest differs from queued batch")
        matches = [request for request in manifest.requests
                   if request.moment_id == job.scene_id]
        if (len(matches) != 1
                or matches[0].expected_revision != job.expected_revision
                or matches[0].estimated_micro_usd
                != round(job.estimated_cost_usd * 1_000_000)):
            raise PermissionError("Premium job does not match approved request")
        story_raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == job.story_id,
            stories.c.owner_id == owner_id,
        ).with_for_update())).scalar_one_or_none()
        if story_raw is None:
            raise PermissionError("Premium story was deleted or transferred")
        draft = StoryDraft.model_validate_json(story_raw)
        if not consent_allows_image_ai(
            draft.image_ai_consent, configured_image_ai_disclosure(),
        ):
            raise PermissionError("Image AI consent is revoked or outdated")
        require_book_art_ready(draft)
        if draft.graph is None or draft.manuscript is None:
            raise PermissionError("Approved premium manuscript is missing")
        current_fingerprint = require_premium_batch_ready(
            manifest=manifest, plan=plan, graph=draft.graph,
            manuscript=draft.manuscript, owner_id=owner_id,
            story_id=job.story_id,
        )
        if current_fingerprint != job.premium_story_fingerprint:
            raise PermissionError("Premium story changed after queueing")
        await fence_worker_ai_effect(
            session, job=job, kind=EffectKind.ILLUSTRATION_AI,
        )
        job = job.model_copy(update={"provider_dispatched_at": now})
        await session.execute(update(illustration_jobs).where(
            illustration_jobs.c.job_id == job_id,
        ).values(payload=job.model_dump_json(), updated_at=now))
        await session.commit()
    return job
