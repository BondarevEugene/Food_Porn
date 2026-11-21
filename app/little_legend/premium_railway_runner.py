"""Opt-in Railway entrypoint for premium child-photo illustration production.

Run only in a dedicated Railway worker service after privacy disclosure,
private R2, pricing and parental consent have been configured.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal

from app.little_legend.art_storage_config import configured_generated_art_store
from app.little_legend.generated_art_store import GeneratedArtS3Settings
from app.little_legend.neon_photo_vault import NeonVaultMetadataRepository
from app.little_legend.neon_premium_photo_consent import (
    NeonPremiumPhotoConsentRepository,
)
from app.little_legend.openai_premium_image_provider import (
    OpenAIPremiumImageProvider,
    OpenAIPremiumImageSettings,
)
from app.little_legend.premium_photo_consent import configured_premium_photo_disclosure
from app.little_legend.premium_worker_runtime import (
    PremiumWorkerDependencies,
    run_premium_worker_loop,
)
from app.little_legend.private_photo_vault import (
    AuthorizedPrivatePhotoVault,
    S3PrivatePhotoStore,
)
from app.little_legend.writer_queue import JobPolicy

logger = logging.getLogger(__name__)


def configured_premium_worker() -> PremiumWorkerDependencies:
    """Validate all mandatory configuration before opening any job lease."""
    if os.environ.get("LL_PREMIUM_WORKER_ENABLED") != "true":
        raise RuntimeError("Premium worker is disabled")
    disclosure = configured_premium_photo_disclosure()
    if not disclosure.ready:
        raise RuntimeError("Final photo AI disclosure must be configured")
    if os.environ.get("LL_PREMIUM_PRICING_APPROVED") != "true":
        raise RuntimeError("Premium pricing has not been approved")
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OpenAI provider key is not configured")
    names = (
        "LITTLE_LEGEND_S3_ENDPOINT_URL",
        "LITTLE_LEGEND_S3_BUCKET",
        "LITTLE_LEGEND_S3_REGION",
        "LITTLE_LEGEND_S3_ACCESS_KEY_ID",
        "LITTLE_LEGEND_S3_SECRET_ACCESS_KEY",
    )
    values = [os.environ.get(name, "").strip() for name in names]
    settings = GeneratedArtS3Settings(*values)
    vault = AuthorizedPrivatePhotoVault(
        metadata=NeonVaultMetadataRepository(),
        objects=S3PrivatePhotoStore(settings),
    )
    policy = JobPolicy(
        max_attempts=3, lease_seconds=600,
        max_estimated_cost_usd=float(
            os.environ.get("LL_PREMIUM_MAX_JOB_COST_USD", "2.00")
        ),
    )
    return PremiumWorkerDependencies(
        provider=OpenAIPremiumImageProvider(OpenAIPremiumImageSettings(api_key=key)),
        store=configured_generated_art_store(),
        references=vault,
        reference_reader=vault,
        policy=policy,
        provider_configured=True,
        private_storage_configured=True,
        price_configured=True,
        photo_consents=NeonPremiumPhotoConsentRepository(),
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    dependencies = configured_premium_worker()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(name, stop.set)
        except NotImplementedError:
            pass
    logger.info("Little Legend premium worker started")
    await run_premium_worker_loop(dependencies=dependencies, stop=stop)


if __name__ == "__main__":
    asyncio.run(main())
