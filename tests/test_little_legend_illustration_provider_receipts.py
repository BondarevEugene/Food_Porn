"""Image receipts are optional and cannot be fabricated from estimates."""
import pytest
from pydantic import ValidationError

from app.little_legend.illustration_provider_receipts import (
    IllustrationProviderResult,
    image_provider_receipt,
)


def test_missing_provider_acknowledgement_keeps_hold() -> None:
    result = image_provider_receipt(
        image=b"png", response_id=None, configured_micro_usd=5000,
    )
    assert result.image == b"png"
    assert result.actual_micro_usd is None
    assert result.provider_reference is None


def test_missing_price_keeps_hold() -> None:
    result = image_provider_receipt(
        image=b"png", response_id="image-123", configured_micro_usd=None,
    )
    assert result.actual_micro_usd is None


def test_explicit_price_and_acknowledgement() -> None:
    result = image_provider_receipt(
        image=b"png", response_id="image-123", configured_micro_usd=5000,
    )
    assert result == IllustrationProviderResult(
        image=b"png", actual_micro_usd=5000,
        provider_reference="image-123",
    )


@pytest.mark.parametrize("price", [-1, True, 1.5])
def test_invalid_price_is_rejected(price: object) -> None:
    with pytest.raises(ValueError):
        image_provider_receipt(
            image=b"png", response_id="image-123",
            configured_micro_usd=price,
        )


def test_invalid_receipt_reference_is_rejected() -> None:
    with pytest.raises(ValidationError):
        image_provider_receipt(
            image=b"png", response_id="x" * 161,
            configured_micro_usd=5000,
        )
