"""Optional provider acknowledgement for an original scene illustration."""
from __future__ import annotations

from pydantic import BaseModel, Field


class IllustrationProviderResult(BaseModel):
    image: bytes = Field(min_length=1)
    actual_micro_usd: int | None = Field(default=None, ge=0)
    provider_reference: str | None = Field(default=None, min_length=1, max_length=160)


def image_provider_receipt(
    *, image: bytes, response_id: str | None,
    configured_micro_usd: int | None,
) -> IllustrationProviderResult:
    """Only an explicitly configured model/size/quality price is usable."""
    if configured_micro_usd is None or not response_id:
        return IllustrationProviderResult(image=image)
    if (
        not isinstance(configured_micro_usd, int)
        or isinstance(configured_micro_usd, bool)
        or configured_micro_usd < 0
    ):
        raise ValueError("Invalid illustration provider price")
    return IllustrationProviderResult(
        image=image, actual_micro_usd=configured_micro_usd,
        provider_reference=response_id,
    )
