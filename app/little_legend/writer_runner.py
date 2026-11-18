"""Operator-only, one-shot Little Legend chapter worker.

Default invocation is a non-billable configuration check. No polling loop,
implicit consent, automatic retry, or deployment startup hook is installed.
"""
from __future__ import annotations

import argparse
import asyncio
import os

from app.little_legend.openai_chapter_provider import (
    OpenAIChapterProvider,
    WriterAdapterSettings,
)
from app.little_legend.text_ai_disclosure import configured_text_ai_disclosure


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Little Legend one-shot writer")
    parser.add_argument(
        "--execute", action="store_true",
        help="Explicitly permit one potentially billable provider request",
    )
    return parser


def validate_operator_configuration(
    *, execute: bool, env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Validate operator intent without revealing credentials or child data."""
    values = os.environ if env is None else env
    if not execute:
        return {"status": "dry_run", "network": "disabled"}
    if values.get("LL_WRITER_ENABLED") != "true":
        raise PermissionError("LL_WRITER_ENABLED=true is required")
    if not values.get("OPENAI_API_KEY", "").strip():
        raise PermissionError("OPENAI_API_KEY is required")
    if not values.get("LL_TEXT_AI_CONSENT_ENABLED") == "true":
        raise PermissionError("Text AI disclosure must be enabled")
    return {"status": "configured", "network": "one_job_only"}


async def execute_one_job() -> dict:
    """Existing worker rechecks each story's consent immediately before dispatch."""
    from openai import AsyncOpenAI

    from app.little_legend.sketch_worker import run_one_writer_job

    disclosure = configured_text_ai_disclosure()
    if not disclosure.ready:
        raise PermissionError("Text AI provider disclosure is incomplete")
    if disclosure.provider.strip().casefold() != "openai":
        raise PermissionError("Configured disclosure does not match OpenAI adapter")
    settings = WriterAdapterSettings(
        enabled=True,
        model=os.environ.get("LL_WRITER_MODEL", "gpt-4o-mini"),
    )
    async with AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"]) as client:
        provider = OpenAIChapterProvider(client=client, settings=settings)
        return await run_one_writer_job(provider)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    state = validate_operator_configuration(execute=args.execute)
    if not args.execute:
        print("Little Legend writer: dry-run only; no provider calls")
        return 0
    result = asyncio.run(execute_one_job())
    # Never print child prose, provider errors or personal metadata.
    print(f"Little Legend writer status: {result['status']}")
    return 0 if result["status"] in {"completed", "idle"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
