"""Fail-closed illustration worker orchestration.

The caller supplies transactional persistence and a private asset store. This
module deliberately has no auto-start: deploy an operator-controlled worker
only after consent, provider configuration and storage are provisioned.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from app.little_legend.image_ai_consent import (
    ImageAIConsent, ImageAIDisclosure, consent_allows_image_ai,
)
from app.little_legend.image_safety import sanitize_image
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.story_graph import SceneNode
from app.little_legend.writer_queue import JobStatus


class Illustrator(Protocol):
    async def generate_scene(
        self, *, scene: SceneNode, hero: str, style: str,
        continuity: str = "",
    ) -> bytes: ...


@dataclass(frozen=True)
class IllustrationContext:
    scene: SceneNode
    hero: str
    style: str
    consent: ImageAIConsent
    disclosure: ImageAIDisclosure
    current_revision: int
    owner_verified: bool
    manuscript_approved: bool


async def run_illustration_job(
    *, job: IllustrationJob, context: IllustrationContext,
    illustrator: Illustrator,
    fence_dispatch: Callable[[IllustrationJob], Awaitable[None]],
    persist_image: Callable[[IllustrationJob, bytes], Awaitable[None]],
    mark_completed: Callable[[IllustrationJob], Awaitable[None]],
) -> None:
    """Execute one claimed job; never retry after an ambiguous dispatch.

    A crash after the durable dispatch fence requires operator reconciliation.
    Persist must be idempotent and private, keyed by job_id. The completion
    callback must check the same lease before committing success.
    """
    if job.status != JobStatus.RUNNING or not job.lease_token:
        raise PermissionError("Illustration job must hold a valid lease")
    if job.provider_dispatched_at is not None:
        raise PermissionError("Previously dispatched job requires reconciliation")
    if not context.owner_verified or not context.manuscript_approved:
        raise PermissionError("Owner and manuscript approval required")
    if not consent_allows_image_ai(context.consent, context.disclosure):
        raise PermissionError("Image AI consent is absent or revoked")
    if job.scene_id != context.scene.id or job.expected_revision != context.current_revision:
        raise PermissionError("Illustration job references a stale manuscript")
    if not context.hero.strip() or not context.style.strip():
        raise ValueError("Illustration context is incomplete")
    await fence_dispatch(job)
    # No retry of this call without explicit reconciliation.
    raw = await illustrator.generate_scene(
        scene=context.scene, hero=context.hero, style=context.style,
    )
    sanitized = sanitize_image(raw)
    await persist_image(job, sanitized.data)
    await mark_completed(job)


async def run_illustration_job_with_private_store(
    *, job: IllustrationJob, context: IllustrationContext,
    illustrator: Illustrator, store: GeneratedArtStore,
    fence_dispatch: Callable[[IllustrationJob], Awaitable[None]],
    mark_completed: Callable[[IllustrationJob], Awaitable[None]],
) -> None:
    """Use the private, deterministic S3 key for idempotent asset persistence.

    The caller must only mark a job complete after the storage write succeeds.
    A failed storage write after provider dispatch is NOT automatically retried.
    """
    async def persist_image(current: IllustrationJob, image: bytes) -> None:
        save_generated_illustration(
            store=store, owner_id=current.owner_id,
            story_id=current.story_id, job_id=current.job_id, data=image,
        )

    await run_illustration_job(
        job=job, context=context, illustrator=illustrator,
        fence_dispatch=fence_dispatch, persist_image=persist_image,
        mark_completed=mark_completed,
    )
