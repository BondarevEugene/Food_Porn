"""Opt-in continuous AI production for Little Legend queued chapters and art.

Separate from the PDF delivery worker. Existing queue claims, consent,
provider-dispatch fences and budget reservations remain authoritative.
Never automatically reclaims a dispatched or ambiguous provider call.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os

from app.little_legend.writer_runner import (
    execute_one_job,
    validate_operator_configuration,
)

logger = logging.getLogger(__name__)


def validate_ai_production(*, mode: str, env: dict[str, str] | None = None) -> None:
    values = os.environ if env is None else env
    if values.get("LL_AI_PRODUCTION_ENABLED") != "true":
        raise PermissionError("LL_AI_PRODUCTION_ENABLED=true is required")
    if mode not in {"writer", "illustration"}:
        raise ValueError("Unsupported production mode")
    if mode == "writer":
        validate_operator_configuration(execute=True, env=values)
        return
    if values.get("LL_ILLUSTRATION_ENABLED") != "true":
        raise PermissionError("LL_ILLUSTRATION_ENABLED=true is required")
    if values.get("LL_IMAGE_AI_CONSENT_ENABLED") != "true":
        raise PermissionError("Image AI disclosure must be enabled")
    if not values.get("OPENAI_API_KEY", "").strip():
        raise PermissionError("OPENAI_API_KEY is required")
    for name in (
        "LITTLE_LEGEND_ART_S3_ENDPOINT",
        "LITTLE_LEGEND_ART_S3_BUCKET",
        "LITTLE_LEGEND_ART_S3_REGION",
        "LITTLE_LEGEND_ART_S3_ACCESS_KEY",
        "LITTLE_LEGEND_ART_S3_SECRET_KEY",
        "LL_ILLUSTRATION_PRICE_MICRO_USD",
    ):
        if not values.get(name, "").strip():
            raise PermissionError(f"{name} is required")
    if not values["LITTLE_LEGEND_ART_S3_ENDPOINT"].startswith("https://"):
        raise PermissionError("Generated-art storage must use HTTPS")
    if int(values["LL_ILLUSTRATION_PRICE_MICRO_USD"]) <= 0:
        raise ValueError("Illustration budget price must be positive")


async def execute_one_illustration() -> bool:
    """Process one existing queue item with private art storage."""
    from openai import AsyncOpenAI

    from app.little_legend.generated_art_store import (
        GeneratedArtS3Settings,
        S3GeneratedArtStore,
    )
    from app.little_legend.illustration_runner import process_next_illustration
    from app.little_legend.openai_illustration_provider import (
        IllustrationSettings,
        OpenAIIllustrationProvider,
    )

    values = os.environ
    settings = GeneratedArtS3Settings(
        endpoint_url=values["LITTLE_LEGEND_ART_S3_ENDPOINT"],
        bucket=values["LITTLE_LEGEND_ART_S3_BUCKET"],
        region=values["LITTLE_LEGEND_ART_S3_REGION"],
        access_key_id=values["LITTLE_LEGEND_ART_S3_ACCESS_KEY"],
        secret_access_key=values["LITTLE_LEGEND_ART_S3_SECRET_KEY"],
    )
    store = S3GeneratedArtStore(settings)
    async with AsyncOpenAI(api_key=values["OPENAI_API_KEY"]) as client:
        provider = OpenAIIllustrationProvider(
            client=client,
            settings=IllustrationSettings(
                enabled=True,
                model=values.get("LL_ILLUSTRATION_MODEL", "gpt-image-1-mini"),
            ),
        )
        return await process_next_illustration(illustrator=provider, store=store)


async def process_cycle(mode: str) -> bool:
    if mode == "illustration":
        return await execute_one_illustration()
    result = await execute_one_job()
    status = result["status"]
    if status == "idle":
        return False
    if status != "completed":
        raise RuntimeError(f"Writer job requires review: {status}")
    return True


async def run(*, mode: str, once: bool = False, idle_seconds: int = 10) -> None:
    validate_ai_production(mode=mode)
    if not 1 <= idle_seconds <= 300:
        raise ValueError("Invalid polling interval")
    while True:
        try:
            worked = await process_cycle(mode)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never automatically re-dispatch a fenced job. The underlying
            # queue only selects claimable work; uncertain effects need review.
            logger.exception("Little Legend %s production cycle failed", mode)
            if once:
                raise
            await asyncio.sleep(30)
            continue
        if once:
            return
        if not worked:
            await asyncio.sleep(idle_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Little Legend opt-in AI queue worker")
    parser.add_argument("--mode", choices=("writer", "illustration"), required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--idle-seconds", type=int, default=10)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(
        mode=args.mode, once=args.once, idle_seconds=args.idle_seconds,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
