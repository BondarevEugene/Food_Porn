"""Durable, owner-scoped illustration jobs in Neon PostgreSQL.

Provider dispatch is fenced before a paid request. Dispatched jobs cannot be
reclaimed automatically after a crash, preventing ambiguous double billing.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime

from pydantic import BaseModel, Field
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
    claim_job,
    finish_job,
)

illustration_metadata = MetaData()
illustration_jobs = Table(
    "little_legend_illustration_jobs", illustration_metadata,
    Column("job_id", String(120), primary_key=True),
    Column("story_id", Integer, nullable=False, index=True),
    Column("owner_id", BigInteger, nullable=False, index=True),
    Column("scene_id", String(100), nullable=False),
    Column("status", String(20), nullable=False, index=True),
    Column("payload", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class IllustrationJob(WriterJob):
    """Reuses the proven lease and dispatch state machine for paid image jobs."""

    premium_manifest_fingerprint: str | None = None
    premium_story_fingerprint: str | None = None


class IllustrationQueuePolicy(BaseModel):
    max_scene_jobs: int = Field(default=40, ge=1, le=40)
    max_estimated_total_usd: float = Field(default=5, gt=0, le=50)


async def enqueue_illustration_jobs(
    *, story_id: int, owner_id: int, scene_ids: list[str],
    estimated_cost_usd: float = 0.05,
    policy: IllustrationQueuePolicy | None = None,
) -> list[str]:
    """Atomically enqueue one job per approved scene; never call AI here."""
    from app.little_legend.image_ai_consent import (
        configured_image_ai_disclosure,
        consent_allows_image_ai,
    )
    from app.little_legend.router import StoryDraft, stories

    policy = policy or IllustrationQueuePolicy()
    if not scene_ids or len(scene_ids) > policy.max_scene_jobs:
        raise ValueError("Invalid number of illustration scenes")
    if len(set(scene_ids)) != len(scene_ids):
        raise ValueError("Duplicate scene IDs")
    if estimated_cost_usd <= 0 or (
        estimated_cost_usd * len(scene_ids) > policy.max_estimated_total_usd
    ):
        raise ValueError("Illustration budget exceeds limit")
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ).with_for_update())).scalar_one_or_none()
        if raw is None:
            raise ValueError("Story not found")
        draft = StoryDraft.model_validate_json(raw)
        if not consent_allows_image_ai(
            draft.image_ai_consent, configured_image_ai_disclosure(),
        ):
            raise PermissionError("Image AI consent is missing or outdated")
        if draft.manuscript is None or draft.graph is None:
            raise PermissionError("Approved manuscript and graph required")
        from app.little_legend.art_preflight import require_book_art_ready

        require_book_art_ready(draft)
        expected = {node.id for node in draft.graph.nodes}
        chapters = {c.scene_id: c for c in draft.manuscript.chapters}
        if (set(scene_ids) != expected or set(chapters) != expected
                or not draft.manuscript.parent_approved
                or any(not c.approved for c in chapters.values())):
            raise PermissionError("Complete approved manuscript required")
        existing = (await session.execute(
            select(illustration_jobs.c.job_id).where(
                illustration_jobs.c.story_id == story_id,
                illustration_jobs.c.owner_id == owner_id,
            )
        )).scalars().all()
        if existing:
            raise PermissionError("Illustration batch already exists")
        ids = []
        for scene_id in scene_ids:
            job = IllustrationJob(
                job_id="lli_" + secrets.token_urlsafe(24),
                story_id=story_id, owner_id=owner_id,
                scene_id=scene_id, expected_revision=chapters[scene_id].revision,
                estimated_cost_usd=estimated_cost_usd,
            )
            await session.execute(insert(illustration_jobs).values(
                job_id=job.job_id, story_id=story_id, owner_id=owner_id,
                scene_id=scene_id, status=job.status.value,
                payload=job.model_dump_json(), created_at=now, updated_at=now,
            ))
            ids.append(job.job_id)
        await session.commit()
    return ids


async def enqueue_premium_illustration_jobs(\n    *, manifest, plan,\n) -> list[str]:\n    """Atomically stage a complete premium batch without dispatching paid AI.\n\n    Premium jobs remain unclaimable until a premium-aware worker and\n    transactional dispatch fence are deployed.\n    """\n    from app.little_legend.art_preflight import require_book_art_ready\n    from app.little_legend.image_ai_consent import (\n        configured_image_ai_disclosure,\n        consent_allows_image_ai,\n    )\n    from app.little_legend.premium_batch_manifest import PremiumBatchManifest\n    from app.little_legend.premium_queue_safety import require_premium_batch_ready\n    from app.little_legend.premium_visual_contract import BookVisualPlan\n    from app.little_legend.router import StoryDraft, stories\n\n    if not isinstance(manifest, PremiumBatchManifest) or not isinstance(plan, BookVisualPlan):\n        raise TypeError("Validated premium manifest and plan are required")\n    now = datetime.now(UTC)\n    async with async_session_maker() as session:\n        raw = (await session.execute(select(stories.c.data).where(\n            stories.c.id == manifest.story_id,\n            stories.c.owner_id == manifest.owner_id,\n        ).with_for_update())).scalar_one_or_none()\n        if raw is None:\n            raise ValueError("Story not found")\n        draft = StoryDraft.model_validate_json(raw)\n        if not consent_allows_image_ai(\n            draft.image_ai_consent, configured_image_ai_disclosure(),\n        ):\n            raise PermissionError("Image AI consent is missing or outdated")\n        require_book_art_ready(draft)\n        if draft.graph is None or draft.manuscript is None:\n            raise PermissionError("Approved manuscript and graph required")\n        fingerprint = require_premium_batch_ready(\n            manifest=manifest, plan=plan, graph=draft.graph,\n            manuscript=draft.manuscript, owner_id=manifest.owner_id,\n            story_id=manifest.story_id,\n        )\n        existing = (await session.execute(select(illustration_jobs.c.job_id).where(\n            illustration_jobs.c.story_id == manifest.story_id,\n            illustration_jobs.c.owner_id == manifest.owner_id,\n        ))).scalars().first()\n        if existing is not None:\n            raise PermissionError("Illustration batch already exists")\n        ids = []\n        for request in manifest.requests:\n            job = IllustrationJob(\n                job_id="lli_" + secrets.token_urlsafe(24),\n                story_id=manifest.story_id, owner_id=manifest.owner_id,\n                scene_id=request.moment_id,\n                expected_revision=request.expected_revision,\n                estimated_cost_usd=request.estimated_micro_usd / 1_000_000,\n                premium_manifest_fingerprint=manifest.fingerprint,\n                premium_story_fingerprint=fingerprint,\n            )\n            await session.execute(insert(illustration_jobs).values(\n                job_id=job.job_id, story_id=job.story_id, owner_id=job.owner_id,\n                scene_id=job.scene_id, status=job.status.value,\n                payload=job.model_dump_json(), created_at=now, updated_at=now,\n            ))\n            ids.append(job.job_id)\n        await session.commit()\n    return ids\n\n\nasync def claim_next_illustration_job(
    policy: JobPolicy,
) -> IllustrationJob | None:
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(illustration_jobs).where(illustration_jobs.c.status.in_([
                JobStatus.QUEUED.value, JobStatus.RETRY_WAIT.value,
                JobStatus.RUNNING.value,
            ])).order_by(illustration_jobs.c.created_at)
            .with_for_update(skip_locked=True).limit(50)
        )).mappings().all()
        for row in rows:
            job = IllustrationJob.model_validate_json(row["payload"])
            if job.premium_manifest_fingerprint is not None:\n                # The legacy worker cannot safely dispatch per-moment premium art.\n                continue\n            try:
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


async def fence_illustration_dispatch(
    *, job_id: str, owner_id: int, token: str,
    expected_art_fingerprint: str | None = None,
) -> IllustrationJob:
    """Persist dispatch marker BEFORE invoking any billable image provider."""
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        raw = (await session.execute(
            select(illustration_jobs.c.payload).where(
                illustration_jobs.c.job_id == job_id,
                illustration_jobs.c.owner_id == owner_id,
            ).with_for_update()
        )).scalar_one_or_none()
        if raw is None:
            raise ValueError("Illustration job not found")
        job = IllustrationJob.model_validate_json(raw)
        if job.premium_manifest_fingerprint is not None:\n            raise PermissionError("Premium dispatch requires a premium-aware fence")\n        if (job.status != JobStatus.RUNNING or job.lease_token != token
                or job.lease_expires_at is None or job.lease_expires_at <= now
                or job.provider_dispatched_at is not None):
            raise PermissionError("Invalid or already dispatched illustration lease")
        # Recheck under the story row lock immediately before a billable call.
        # A revoked consent or edited chapter must block dispatch even when
        # the worker loaded an older snapshot.
        from app.little_legend.image_ai_consent import (
            configured_image_ai_disclosure,
            consent_allows_image_ai,
        )
        from app.little_legend.router import StoryDraft, stories

        story_raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == job.story_id,
            stories.c.owner_id == owner_id,
        ).with_for_update())).scalar_one_or_none()
        if story_raw is None:
            raise PermissionError("Story was deleted or ownership changed")
        draft = StoryDraft.model_validate_json(story_raw)
        if not consent_allows_image_ai(
            draft.image_ai_consent, configured_image_ai_disclosure(),
        ):
            raise PermissionError("Image AI consent was revoked")
        if draft.graph is None or draft.manuscript is None:
            raise PermissionError("Approved story is unavailable")
        chapter = next((
            chapter for chapter in draft.manuscript.chapters
            if chapter.scene_id == job.scene_id
        ), None)
        if (not draft.manuscript.parent_approved or chapter is None
                or not chapter.approved
                or chapter.revision != job.expected_revision
                or job.scene_id not in {node.id for node in draft.graph.nodes}):
            raise PermissionError("Story approval or revision changed")
        # Parent edits may invalidate the visual identity or another chapter
        # after queueing. Revalidate the entire book under the story row lock
        # immediately before the irreversible paid-provider dispatch fence.
        from app.little_legend.art_preflight import require_book_art_ready

        require_book_art_ready(draft)
        if expected_art_fingerprint is not None:
            from app.little_legend.art_dispatch_snapshot import (
                art_dispatch_fingerprint,
            )

            actual_fingerprint = art_dispatch_fingerprint(draft, job.scene_id)
            if actual_fingerprint != expected_art_fingerprint:
                raise PermissionError(
                    "Art context changed after worker snapshot; dispatch cancelled"
                )
        from app.little_legend.production_effect_ledger import EffectKind
        from app.little_legend.worker_ai_fence import fence_worker_ai_effect

        await fence_worker_ai_effect(
            session, job=job, kind=EffectKind.ILLUSTRATION_AI,
        )
        job = job.model_copy(update={"provider_dispatched_at": now})
        await session.execute(update(illustration_jobs).where(
            illustration_jobs.c.job_id == job_id,
        ).values(payload=job.model_dump_json(), updated_at=now))
        await session.commit()
    return job


async def complete_illustration_job(
    *, job_id: str, owner_id: int, token: str,
    success: bool, policy: JobPolicy,
    actual_micro_usd: int | None = None,
    provider_reference: str | None = None,
) -> IllustrationJob:
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        raw = (await session.execute(
            select(illustration_jobs.c.payload).where(
                illustration_jobs.c.job_id == job_id,
                illustration_jobs.c.owner_id == owner_id,
            ).with_for_update()
        )).scalar_one_or_none()
        if raw is None:
            raise ValueError("Illustration job not found")
        job = IllustrationJob.model_validate_json(raw)
        if job.provider_dispatched_at is None:
            raise PermissionError("Provider dispatch was not fenced")
        changed = finish_job(
            job, token=token, success=success, policy=policy,
            retryable=False, now=now,
        )
        from app.little_legend.production_effect_ledger import EffectKind
        from app.little_legend.worker_charge_receipts import (
            settle_worker_receipt,
            validate_provider_receipt,
        )

        has_receipt = validate_provider_receipt(
            actual_micro_usd=actual_micro_usd,
            provider_reference=provider_reference,
        )
        if has_receipt:
            if not success:
                raise ValueError("Cannot settle failed provider result")
            await settle_worker_receipt(
                session,
                job=job,
                kind=EffectKind.ILLUSTRATION_AI,
                actual_micro_usd=actual_micro_usd,
                provider_reference=provider_reference,
            )
        await session.execute(update(illustration_jobs).where(
            illustration_jobs.c.job_id == job_id,
        ).values(
            status=changed.status.value, payload=changed.model_dump_json(),
            updated_at=now,
        ))
        await session.commit()
    return IllustrationJob.model_validate(changed)


async def list_owner_illustration_jobs(
    *, story_id: int, owner_id: int,
) -> list[IllustrationJob]:
    """Return only metadata for this owner's story; never expose lease tokens."""
    from app.little_legend.router import stories

    async with async_session_maker() as session:
        owned = (await session.execute(select(stories.c.id).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ))).scalar_one_or_none()
        if owned is None:
            raise ValueError("Story not found")
        rows = (await session.execute(select(illustration_jobs.c.payload).where(
            illustration_jobs.c.story_id == story_id,
            illustration_jobs.c.owner_id == owner_id,
        ).order_by(illustration_jobs.c.created_at))).scalars().all()
    return [IllustrationJob.model_validate_json(raw) for raw in rows]
