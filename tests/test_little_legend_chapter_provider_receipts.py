"""Provider usage must be priced explicitly; missing rates retain holds."""
from decimal import Decimal

import pytest

from app.little_legend.chapter_provider_receipts import (
    ChapterProviderResult,
    calculate_usage_micro_usd,
    verified_chapter_receipt,
)


def test_token_usage_is_rounded_up_in_micro_usd() -> None:
    assert calculate_usage_micro_usd(
        prompt_tokens=1000, completion_tokens=500,
        input_usd_per_million=Decimal("0.15"),
        output_usd_per_million=Decimal("0.60"),
    ) == 450


def test_fractional_micro_usd_is_rounded_up() -> None:
    assert calculate_usage_micro_usd(
        prompt_tokens=1, completion_tokens=0,
        input_usd_per_million=Decimal("0.15"),
        output_usd_per_million=Decimal("0"),
    ) == 1


@pytest.mark.parametrize("count", [-1, True, 1.2])
def test_invalid_token_usage_is_rejected(count: object) -> None:
    with pytest.raises(ValueError, match="token usage"):
        calculate_usage_micro_usd(
            prompt_tokens=count, completion_tokens=0,
            input_usd_per_million=Decimal("0.1"),
            output_usd_per_million=Decimal("0.1"),
        )


@pytest.mark.parametrize("rate", ["-1", "NaN", "Infinity"])
def test_invalid_token_rates_are_rejected(rate: str) -> None:
    with pytest.raises(ValueError, match="token rates"):
        calculate_usage_micro_usd(
            prompt_tokens=1, completion_tokens=1,
            input_usd_per_million=Decimal(rate),
            output_usd_per_million=Decimal("0.1"),
        )


def test_missing_receipt_remains_unsettled() -> None:
    result = verified_chapter_receipt(
        text="A story", provider_reference="chatcmpl-123",
        prompt_tokens=100, completion_tokens=100,
        input_usd_per_million=None,
        output_usd_per_million=None,
    )
    assert result == ChapterProviderResult(text="A story")
    assert result.actual_micro_usd is None


def test_complete_receipt_contains_provider_reference() -> None:
    result = verified_chapter_receipt(
        text="A story", provider_reference="chatcmpl-123",
        prompt_tokens=100, completion_tokens=100,
        input_usd_per_million=Decimal("0.15"),
        output_usd_per_million=Decimal("0.60"),
    )
    assert result.actual_micro_usd == 75
    assert result.provider_reference == "chatcmpl-123"
