"""Read-only precheckout, explicitly separated from a payable order."""
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
    price_configured: bool = False
    edition_available: bool = False
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
    """Show the current CRM price without creating a charge or a job.

    A price preview cannot be reused as an immutable invoice. Prices must be
    snapped into an owner-scoped order when checkout is implemented.
    """
    if story_id <= 0:
        raise ValueError("Invalid story ID")
    catalog = await crm_book_catalog()
    offer = next(item for item in catalog.offers if item.edition == edition)
    if edition == BookEdition.PRINT:
        reason = "print_production_not_certified"
    elif offer.price_minor is None:
        reason = "price_not_configured"
    else:
        reason = "verified_payment_integration_pending"
    return BookPrecheckout(
        story_id=story_id,
        edition=edition,
        price_minor=offer.price_minor,
        price_configured=offer.price_minor is not None,
        edition_available=offer.available,
        reason=reason,
    )
