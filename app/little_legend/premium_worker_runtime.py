"""Operator-controlled premium production worker.

Fail closed before claiming a lease unless the image provider, private R2
store, identity reference resolver and billing configuration are ready.
The worker does not start automatically on import.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.little_legend.generated_art_store import GeneratedArtStore
from app.little_legend.illustration_queue_store import (
    IllustrationJob,
    complete_illustration_job,
)
from app.little_legend.premium_dispatch_store import (
    claim_next_premium_illustration_job,
    fence_premium_illustration_dispatch,
)
from app.little_legend.premium_image_runner import (
    PremiumImageProvider,
    run_restored_premium_image_job,
)
from app.little_legend.premium_photo_consent import (
    PremiumPhotoConsent,
    configured_premium_photo_disclosure,
    premium_photo_consent_allows_transfer,
)
from app.little_legend.premium_private_reference import PrivateReferenceReader
from app.little_legend.writer_queue import JobPolicy

logger = logging.getLogger(__name__)


class PremiumPhotoConsentResolver(Protocol):
    async def get_photo_consent(
        self, *, owner_id: int, story_id: int,
    ) -> PremiumPhotoConsent: ...


class PremiumReferenceResolver(Protocol):
    async def check_access(
        self, *, owner_id: int, story_id: int, reference_ids: set[str],
    ) -> None: ...


@dataclass(frozen=True)
class PremiumWorkerDependencies:
    provider: PremiumImageProvider
    store: GeneratedArtStore
    references: PremiumReferenceResolver
    reference_reader: PrivateReferenceReader
    policy: JobPolicy
    provider_configured: bool
    private_storage_configured: bool
    price_configured: bool
    photo_consents: PremiumPhotoConsentResolver | None = None

    def require_ready(self) -> None:
        if not all((
            self.provider_configured,
            self.private_storage_configured,
            self.price_configured,
        )):
            raise RuntimeError(
                "Premium provider, private storage and pricing must be configured"
            )


async def run_premium_worker_once(
    *, dependencies: PremiumWorkerDependencies,
    claim: Callable[..., Awaitable[IllustrationJob | None]] = (
        claim_next_premium_illustration_job
    ),
    fence: Callable[..., Awaitable[IllustrationJob]] = (
        fence_premium_illustration_dispatch
    ),
    complete: Callable[..., Awaitable[IllustrationJob]] = (
        complete_illustration_job
    ),
) -> bool:
    """Process at most one job; no implicit retry of dispatched paid calls."""
    dependencies.require_ready()
    if dependencies.photo_consents is None or not configured_premium_photo_disclosure().ready:
        raise PermissionError("Premium child-photo AI consent is not configured")
    job = await claim(policy=dependencies.policy)
    if job is None:
        return False
    from app.little_legend.premium_job_context import restore_premium_job_context

    consent = await dependencies.photo_consents.get_photo_consent(
        owner_id=job.owner_id, story_id=job.story_id,
    )
    if not premium_photo_consent_allows_transfer(
        consent, configured_premium_photo_disclosure(),
    ):
        raise PermissionError("Parent has not authorized AI photo transfer")
    context = restore_premium_job_context(job)
    reference_ids = {
        request.reference_id for request in context.manifest.requests
    }
    # Check ALL reference assets before the irreversible provider fence.
    # A missing child photo must never result in a billable AI request.
    await dependencies.references.check_access(
        owner_id=job.owner_id,
        story_id=job.story_id,
        reference_ids=reference_ids,
    )
    await run_restored_premium_image_job(
        job=job,
        provider=dependencies.provider,
        reference_reader=dependencies.reference_reader,
        store=dependencies.store,
        policy=dependencies.policy,
        fence_dispatch=fence,
        complete_job=complete,
    )
    return True


async def run_premium_worker_loop(
    *, dependencies: PremiumWorkerDependencies,
    stop: asyncio.Event,
    poll_seconds: float = 5.0,
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    """Bounded polling, no recursive retries, safe stop for Railway shutdown."""
    if not 1 <= poll_seconds <= 60:
        raise ValueError("Premium worker poll interval must be 1..60 seconds")
    dependencies.require_ready()
    while not stop.is_set():
        try:
            processed = await run_premium_worker_once(dependencies=dependencies)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Do not log prompts, photo bytes, reference IDs or provider secrets.
            logger.exception("Premium worker job failed; reconciliation may be required")
            if on_error is not None:
                on_error(exc)
            processed = False
        if processed:
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass


def premium_worker_health(*, dependencies: PremiumWorkerDependencies) -> dict:
    """Configuration-only status, never includes customer or secret data."""
    return {
        "ready": all((
            dependencies.provider_configured,
            dependencies.private_storage_configured,
            dependencies.price_configured,
        )),
        "provider_configured": dependencies.provider_configured,
        "private_storage_configured": dependencies.private_storage_configured,
        "price_configured": dependencies.price_configured,
        "checked_at": datetime.now(UTC).isoformat(),
    }
