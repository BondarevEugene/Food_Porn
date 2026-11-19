"""Fail-closed commercial catalog for two Little Legend book editions.

All prices are administrator-supplied integer kopecks. This module quotes
products only; it does not accept payments or certify print readiness.
"""
from __future__ import annotations

import os
from enum import StrEnum

from pydantic import BaseModel, Field


class BookEdition(StrEnum):
    DIGITAL = "digital"
    PRINT = "print"


class EditionOffer(BaseModel):
    edition: BookEdition
    currency: str = "UAH"
    price_minor: int | None = Field(default=None, ge=1)
    available: bool
    reason: str | None = None
    includes: tuple[str, ...]


class BookCatalog(BaseModel):
    offers: list[EditionOffer]
    checkout_enabled: bool = False


def _configured_price(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError(f"Invalid price configuration: {name}")
    amount = int(raw)
    if not 100 <= amount <= 100_000_000:
        raise ValueError(f"Price outside configured bounds: {name}")
    return amount


def book_catalog() -> BookCatalog:
    """Quote only configured editions; do not imply an operational checkout."""
    digital = _configured_price("LITTLE_LEGEND_DIGITAL_PRICE_KOP")
    physical = _configured_price("LITTLE_LEGEND_PRINT_PRICE_KOP")
    return BookCatalog(offers=[
        EditionOffer(
            edition=BookEdition.DIGITAL,
            price_minor=digital,
            available=digital is not None,
            reason=None if digital is not None else "price_not_configured",
            includes=("illustrated_pdf", "private_telegram_delivery"),
        ),
        EditionOffer(
            edition=BookEdition.PRINT,
            price_minor=physical,
            available=False,
            reason="print_production_not_certified",
            includes=("illustrated_pdf", "physical_print", "shipping"),
        ),
    ])


def quote_edition(edition: BookEdition) -> EditionOffer:
    offer = next(item for item in book_catalog().offers if item.edition == edition)
    if not offer.available:
        raise PermissionError(offer.reason or "edition_unavailable")
    return offer


async def crm_book_catalog() -> BookCatalog:
    """Read persisted Mini CRM prices, not stale per-worker environment values."""
    from sqlalchemy import select

    from app.database.models import AppSetting
    from app.database.session import async_session_maker

    keys = {
        BookEdition.DIGITAL: "little_legend_digital_price_uah",
        BookEdition.PRINT: "little_legend_print_price_uah",
    }
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(AppSetting.key, AppSetting.value).where(
                AppSetting.key.in_(tuple(keys.values())),
            )
        )).all()
    stored = dict(rows)
    catalog = book_catalog()
    for offer in catalog.offers:
        raw = stored.get(keys[offer.edition])
        if raw is None:
            continue
        if not raw.isascii() or not raw.isdecimal() or not 0 <= int(raw) <= 100000:
            raise ValueError("Invalid CRM edition price")
        amount = int(raw)
        offer.price_minor = amount * 100 if amount else None
        if offer.edition == BookEdition.DIGITAL:
            offer.available = amount > 0
            offer.reason = None if amount else "price_not_configured"
    return catalog
