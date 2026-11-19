"""Validated provider output with usage-derived charge, never an estimate.

A provider response without known model rates is not treated as a verified
receipt; its existing financial reservation stays held for reconciliation.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from pydantic import BaseModel, Field


class ChapterProviderResult(BaseModel):
    text: str = Field(min_length=1)
    actual_micro_usd: int | None = Field(default=None, ge=0)
    provider_reference: str | None = Field(default=None, min_length=1, max_length=160)


def calculate_usage_micro_usd(
    *, prompt_tokens: int, completion_tokens: int,
    input_usd_per_million: Decimal, output_usd_per_million: Decimal,
) -> int:
    if any(
        isinstance(v, bool) or not isinstance(v, int) or v < 0
        for v in (prompt_tokens, completion_tokens)
    ):
        raise ValueError("Invalid token usage")
    if any(not rate.is_finite() or rate < 0 for rate in (
        input_usd_per_million, output_usd_per_million,
    )):
        raise ValueError("Invalid token rates")
    return int((
        Decimal(prompt_tokens) * input_usd_per_million
        + Decimal(completion_tokens) * output_usd_per_million
    ).to_integral_value(rounding=ROUND_CEILING))


def verified_chapter_receipt(
    *, text: str, provider_reference: str | None,
    prompt_tokens: int | None, completion_tokens: int | None,
    input_usd_per_million: Decimal | None,
    output_usd_per_million: Decimal | None,
) -> ChapterProviderResult:
    if (
        not provider_reference or prompt_tokens is None
        or completion_tokens is None or input_usd_per_million is None
        or output_usd_per_million is None
    ):
        return ChapterProviderResult(text=text)
    amount = calculate_usage_micro_usd(
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
        input_usd_per_million=input_usd_per_million,
        output_usd_per_million=output_usd_per_million,
    )
    return ChapterProviderResult(
        text=text, actual_micro_usd=amount,
        provider_reference=provider_reference,
    )
