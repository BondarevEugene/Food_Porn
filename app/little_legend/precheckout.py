"""Read-only precheckout offer; never confuses an estimate with a paid order."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.little_legend.commercial_catalog import (
    BookEdition,
    crm_book_catalog,
)


class BookPrecheckout(BaseModel):
    story_id: int = Field(gt=0)
    edition: BookEdition
    currency: str = "UAH"
    price_minor: int | None = Field(default=None, ge=1)
    payment_enabled: bool = False
    production_enabled: bool = False
    reason: str
    requires: tuple[str, ...] = (
        "immutable_order_quote",
        "verified_payment_receipt",
        "idempotent_production_gate",
    )


async def preview_book_precheckout(
    *, story_id: int, edition: BookEdition,
) -> BookPrecheckout:
    """No side effects: a quote preview is not authorization to produce."""
    if story_id <= 0:
        raise ValueError("Invalid story ID")
    catalog = await crm_book_catalog()
    offer = next(item for item in catalog.offers if item.edition == edition)
    return BookPrecheckout(
        story_id=story_id,
        edition=edition,
        price_minor=offer.price_minor,
        reason=(
            "print_production_not_certified"
            if edition == BookEdition.PRINT
            else "verified_payment_integration_pending"
        ),
    )
