"""One-shot illustration queue runner for an explicitly configured worker process.

No automatic startup or background loop. The caller controls polling cadence,
concurrency, provider credentials and deployment. One invocation claims at most
one job, and never retries a provider-dispatched job.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.database.session import async_session_maker
from app.little_legend.blueprint import BookBlueprint
from app.little_legend.generated_art_store import GeneratedArtStore, save_generated_illustration
from app.little_legend.illustration_queue_store import (
    claim_next_illustration_job,
    complete_illustration_job,
    fence_illustration_dispatch,
)
from app.little_legend.illustration_worker import (
    IllustrationContext,
    Illustrator,
    run_illustration_job,
)
from app.little_legend.image_ai_consent import configured_image_ai_disclosure
from app.little_legend.router import StoryDraft, stories
from app.little_legend.story_graph import SceneNode
from app.little_legend.writer_queue import JobPolicy


def fictional_character_continuity(blueprint: BookBlueprint | None) -> str:
    """Use only textual fictional character notes; never transmit photo references."""
    if blueprint is None:
        return ""
    hero = next((c for c in blueprint.characters if c.role == "hero"), None)
    if hero is None:
        return ""
    notes = [hero.appearance.strip(), hero.visual_identity_notes.strip()]
    return " ".join(note for note in notes if note)[:1200]


def production_character_continuity(blueprint: BookBlueprint | None) -> str:
    """Build one stable character contract for every chapter of a book.

    Only parent-supplied textual traits are used. The existing text-only
    provider cannot guarantee likeness and receives no photo or URL.
    """
    if blueprint is None:
        return ""
    hero = next((person for person in blueprint.characters if person.role == "hero"), None)
    if hero is None:
        return ""
    appearance = hero.appearance.strip()
    identity_notes = hero.visual_identity_notes.strip()
    if not appearance and not identity_notes:
        return ""
    clauses = [
        "ONE RECURRING FICTIONAL HERO: keep the same facial features, hair, "
        "apparent age, body proportions and distinguishing marks in every scene.",
    ]
    if appearance:
        clauses.append(f"Approved appearance: {appearance}")
    if identity_notes:
        clauses.append(f"Fixed visual identity: {identity_notes}")
    clauses.append(
        "Change only pose, expression, camera angle, setting and story-required "
        "outfit; never invent new permanent physical traits."
    )
    contract = " ".join(clauses)
    if len(contract) > 1200:
        raise ValueError("Character continuity exceeds provider limit")
    return contract


def directed_scene_for_provider(scene: SceneNode) -> SceneNode:
    """Include approved scene composition in the production provider input.

    The legacy provider reads scene.summary, not illustration_prompt. Return a
    copy so the stored story graph is never mutated by generation.
    """
    action = scene.illustration_prompt.strip()
    summary = scene.summary.strip()
    if not action:
        if len(summary) > 2000:
            raise ValueError("Scene summary exceeds provider prompt limit")
        return scene
    if not summary:
        raise ValueError("Illustration scene has no narrative summary")
    combined = f"Scene action and composition: {action}. Story context: {summary}"
    if len(combined) > 2000:
        raise ValueError("Scene-specific illustration description is oversized")
    return scene.model_copy(update={"summary": combined})


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
    from app.little_legend.art_dispatch_snapshot import art_dispatch_fingerprint
    from app.little_legend.reviewed_identity_prompt import reviewed_identity_continuity

    art_fingerprint = art_dispatch_fingerprint(draft, job.scene_id)
    context = IllustrationContext(
        scene=directed_scene_for_provider(scene), hero=draft.hero,
        style=(draft.blueprint.controls.illustration_style
               if draft.blueprint else "storybook"),
        consent=draft.image_ai_consent,
        disclosure=configured_image_ai_disclosure(),
        current_revision=chapter.revision,
        owner_verified=True,
        continuity=reviewed_identity_continuity(
            blueprint=draft.blueprint, bible=draft.identity_bible, hero_name=draft.hero,
        ),
        manuscript_approved=(
            draft.manuscript.parent_approved and chapter.approved
        ),
    )

    async def fence(current):
        await fence_illustration_dispatch(
            job_id=current.job_id, owner_id=current.owner_id,
            token=current.lease_token,
            expected_art_fingerprint=art_fingerprint,
        )

    async def complete(
        current, *, actual_micro_usd=None, provider_reference=None,
    ):
        await complete_illustration_job(
            job_id=current.job_id, owner_id=current.owner_id,
            token=current.lease_token, success=True, policy=policy,
            actual_micro_usd=actual_micro_usd,
            provider_reference=provider_reference,
        )

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
