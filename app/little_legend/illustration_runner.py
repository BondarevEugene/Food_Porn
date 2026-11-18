"""One-shot illustration queue runner for an explicitly configured worker process.

No automatic startup or background loop. The caller controls polling cadence,
concurrency, provider credentials and deployment. One invocation claims at most
one job, and never retries a provider-dispatched job.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.database.session import async_session_maker
from app.little_legend.generated_art_store import GeneratedArtStore
from app.little_legend.image_ai_consent import configured_image_ai_disclosure
from app.little_legend.illustration_queue_store import (
    claim_next_illustration_job, complete_illustration_job,
    fence_illustration_dispatch,
)
from app.little_legend.illustration_worker import (
    IllustrationContext, Illustrator, run_illustration_job_with_private_store,
)
from app.little_legend.router import StoryDraft, stories
from app.little_legend.writer_queue import JobPolicy


async def process_next_illustration(
    *, illustrator: Illustrator, store: GeneratedArtStore,
    policy: JobPolicy | None = None,
) -> bool:
    """Process at most one job; return False when no claimable job exists.

    If the provider or storage fails after the durable dispatch marker, leave
    the job for operator reconciliation rather than risking a second charge.
    """
    policy = policy or JobPolicy()
    job = await claim_next_illustration_job(policy)
    if job is None:
        return False
    async with async_session_maker() as session:
        raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == job.story_id,
            stories.c.owner_id == job.owner_id,
        ))).scalar_one_or_none()
    if raw is None:
        raise PermissionError("Story no longer belongs to job owner")
    draft = StoryDraft.model_validate_json(raw)
    if draft.graph is None or draft.manuscript is None:
        raise PermissionError("Story manuscript is unavailable")
    scene = next((node for node in draft.graph.nodes if node.id == job.scene_id), None)
    chapter = next((
        item for item in draft.manuscript.chapters
        if item.scene_id == job.scene_id
    ), None)
    if scene is None or chapter is None:
        raise PermissionError("Illustration scene is no longer available")
    context = IllustrationContext(
        scene=scene, hero=draft.hero,
        style=(draft.blueprint.controls.illustration_style
               if draft.blueprint else "storybook"),
        consent=draft.image_ai_consent,
        disclosure=configured_image_ai_disclosure(),
        current_revision=chapter.revision,
        owner_verified=True,
        manuscript_approved=(
            draft.manuscript.parent_approved and chapter.approved
        ),
    )

    async def fence(current):
        await fence_illustration_dispatch(
            job_id=current.job_id, owner_id=current.owner_id,
            token=current.lease_token,
        )

    async def complete(current):
        await complete_illustration_job(
            job_id=current.job_id, owner_id=current.owner_id,
            token=current.lease_token, success=True, policy=policy,
        )

    class AsyncStore:
        async def _put(self, *, key, data, content_type):
            await asyncio.to_thread(
                store.put, key=key, data=data, content_type=content_type,
            )

        def put(self, *, key, data, content_type):
            # Called by synchronous adapter inside the event loop.
            # S3 upload is blocking; a dedicated async wrapper is below.
            raise RuntimeError("Use asynchronous private-store persistence")

    from app.little_legend.generated_art_store import save_generated_illustration
    from app.little_legend.illustration_worker import run_illustration_job

    async def persist(current, data):
        await asyncio.to_thread(
            save_generated_illustration,
            store=store, owner_id=current.owner_id,
            story_id=current.story_id, job_id=current.job_id, data=data,
        )

    await run_illustration_job(
        job=job, context=context, illustrator=illustrator,
        fence_dispatch=fence, persist_image=persist,
        mark_completed=complete,
    )
    return True
