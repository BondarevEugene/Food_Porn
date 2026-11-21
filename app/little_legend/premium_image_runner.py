"""Provider-neutral premium illustration runner with private R2 persistence.

The caller injects the configured paid image provider and the transactional
dispatch fence. No provider call occurs before the durable fence commits.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from app.little_legend.generated_art_store import (
    GeneratedArtStore,
    save_generated_illustration,
)
from app.little_legend.illustration_provider_receipts import IllustrationProviderResult
from app.little_legend.illustration_queue_store import IllustrationJob
from app.little_legend.image_safety import sanitize_image
from app.little_legend.premium_batch_manifest import (
    PremiumArtRequest,
    PremiumBatchManifest,
)
from app.little_legend.premium_visual_contract import BookVisualPlan
from app.little_legend.writer_queue import JobPolicy, JobStatus


class PremiumImageProvider(Protocol):
    async def generate_premium_image(
        self, *, request: PremiumArtRequest, plan: BookVisualPlan,
    ) -> IllustrationProviderResult: ...


async def run_premium_image_job(
    *, job: IllustrationJob,
    manifest: PremiumBatchManifest,
    plan: BookVisualPlan,
    provider: PremiumImageProvider,
    store: GeneratedArtStore,
    policy: JobPolicy,
    fence_dispatch: Callable[..., Awaitable[IllustrationJob]],
    complete_job: Callable[..., Awaitable[IllustrationJob]],
) -> str:
    """Run one claimed premium slot, storing only a sanitized private JPEG.

    Provider errors after dispatch are intentionally propagated: never
    automatically retry an ambiguous paid call. The existing job lease,
    provider dispatch marker and effect ledger remain for reconciliation.
    """
    if (job.status != JobStatus.RUNNING or not job.lease_token
            or job.provider_dispatched_at is not None
            or job.lease_expires_at is None
            or not job.premium_manifest_fingerprint
            or not job.premium_story_fingerprint):
        raise PermissionError("Premium job requires a fresh undispatched lease")
    if (job.owner_id != manifest.owner_id
            or job.story_id != manifest.story_id
            or job.premium_manifest_fingerprint != manifest.fingerprint
            or manifest.genre != plan.genre.value):
        raise PermissionError("Premium job manifest or genre mismatch")
    matches = [item for item in manifest.requests if item.moment_id == job.scene_id]
    if len(matches) != 1:
        raise PermissionError("Premium illustration slot is missing or ambiguous")
    request = matches[0]
    if (request.expected_revision != job.expected_revision
            or request.estimated_micro_usd
            != round(job.estimated_cost_usd * 1_000_000)):
        raise PermissionError("Premium request revision or cost changed")
    # The durable dispatch fence rechecks the live story, parental consent,
    # identity, budget and lease under database locks before this paid call.
    fenced = await fence_dispatch(
        job_id=job.job_id, owner_id=job.owner_id, token=job.lease_token,
        manifest=manifest, plan=plan,
    )
    if (fenced.job_id != job.job_id or fenced.lease_token != job.lease_token
            or fenced.provider_dispatched_at is None):
        raise PermissionError("Premium dispatch fence did not commit")
    receipt = await provider.generate_premium_image(request=request, plan=plan)
    if not isinstance(receipt, IllustrationProviderResult):
        raise ValueError("Premium provider returned an invalid receipt")
    image = sanitize_image(receipt.image)
    key = save_generated_illustration(
        store=store, owner_id=job.owner_id, story_id=job.story_id,
        job_id=job.job_id, data=image.data,
    )
    await complete_job(
        job_id=job.job_id, owner_id=job.owner_id, token=job.lease_token,
        success=True, policy=policy,
        actual_micro_usd=receipt.actual_micro_usd,
        provider_reference=receipt.provider_reference,
    )
    return key
