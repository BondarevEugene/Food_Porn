"""Precheckout never claims a charge, paid order or production authorization."""
import pytest

from app.little_legend import precheckout
from app.little_legend.commercial_catalog import (
    BookCatalog,
    BookEdition,
    EditionOffer,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("edition", [BookEdition.DIGITAL, BookEdition.PRINT])
async def test_preview_is_not_payment_or_production(monkeypatch, edition):
    async def catalog():
        return BookCatalog(offers=[
            EditionOffer(edition=BookEdition.DIGITAL, available=True,
                         price_minor=129900, includes=("illustrated_pdf",)),
            EditionOffer(edition=BookEdition.PRINT, available=False,
                         price_minor=299900, includes=("physical_print",)),
        ])
    monkeypatch.setattr(precheckout, "crm_book_catalog", catalog)
    result = await precheckout.preview_book_precheckout(
        story_id=12, edition=edition,
    )
    assert not result.payment_enabled
    assert not result.production_enabled
    assert "verified_payment_receipt" in result.requires
    assert result.price_minor == (129900 if edition == BookEdition.DIGITAL else 299900)
    if edition == BookEdition.PRINT:
        assert result.reason == "print_production_not_certified"


@pytest.mark.asyncio
async def test_precheckout_rejects_invalid_story():
    with pytest.raises(ValueError):
        await precheckout.preview_book_precheckout(
            story_id=0, edition=BookEdition.DIGITAL,
        )


@pytest.mark.asyncio
async def test_unconfigured_price_is_explicitly_not_purchasable(monkeypatch):
    async def catalog():
        return BookCatalog(offers=[
            EditionOffer(edition=BookEdition.DIGITAL, available=False,
                         reason="price_not_configured",
                         includes=("illustrated_pdf",)),
            EditionOffer(edition=BookEdition.PRINT, available=False,
                         reason="print_production_not_certified",
                         includes=("physical_print",)),
        ])
    monkeypatch.setattr(precheckout, "crm_book_catalog", catalog)
    result = await precheckout.preview_book_precheckout(
        story_id=42, edition=BookEdition.DIGITAL,
    )
    assert result.price_minor is None
    assert not result.price_configured
    assert not result.edition_available
    assert result.reason == "price_not_configured"
    assert not result.payment_enabled
    assert not result.production_enabled


@pytest.mark.asyncio
async def test_configured_price_does_not_unlock_payment(monkeypatch):
    async def catalog():
        return BookCatalog(offers=[
            EditionOffer(edition=BookEdition.DIGITAL, available=True,
                         price_minor=120000, includes=("illustrated_pdf",)),
        ])
    monkeypatch.setattr(precheckout, "crm_book_catalog", catalog)
    result = await precheckout.preview_book_precheckout(
        story_id=42, edition=BookEdition.DIGITAL,
    )
    assert result.price_configured
    assert result.edition_available
    assert result.reason == "verified_payment_integration_pending"
    assert not result.payment_enabled
