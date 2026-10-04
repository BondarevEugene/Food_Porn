"""Compute the amount from measured API token usage and a five-percent margin."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

IMAGE_RATES = {
    # USD per million tokens: text input, image input, text output, image output.
    "gpt-image-1.5": ("5", "8", "10", "32"),
    "gpt-image-2.5-sunburst": ("5", "8", "0", "30"),
    "gpt-image-2.5-flare": ("5", "8", "0", "30"),
}


def image_cost_usd(usage: Any, model: str) -> Decimal:
    if model not in IMAGE_RATES:
        raise ValueError(f"No verified token prices configured for image model {model!r}")
    if usage is None or usage.input_tokens_details is None:
        raise ValueError("Image response did not report token usage")
    details = usage.input_tokens_details
    output = usage.output_tokens_details
    if output is None:
        output_image, output_text = usage.output_tokens, 0
    else:
        output_image, output_text = output.image_tokens, output.text_tokens
    if model.startswith("gpt-image-2.5") and output_text:
        raise ValueError("Cannot price text output for this image model")
    rates = [Decimal(value) for value in IMAGE_RATES[model]]
    amounts = [details.text_tokens, details.image_tokens, output_text, output_image]
    if any(value is None or value < 0 for value in amounts):
        raise ValueError("Incomplete image token usage")
    return sum((Decimal(count) * price for count, price in zip(amounts, rates, strict=True)), Decimal(0)) / Decimal(1_000_000)


def checkout_price_uah(cost_usd: Decimal, usd_exchange_rate: float) -> Decimal:
    if cost_usd <= 0 or usd_exchange_rate <= 0:
        raise ValueError("Valid positive API cost and exchange rate required")
    return (cost_usd * Decimal(str(usd_exchange_rate)) * Decimal("1.05")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
