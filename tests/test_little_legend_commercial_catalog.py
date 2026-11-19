"""Two-edition catalog must never invent prices or enable unverified print."""
import pytest

from app.little_legend.commercial_catalog import (
    BookEdition,
    book_catalog,
    quote_edition,
)


def test_catalog_is_unpriced_and_checkout_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LITTLE_LEGEND_DIGITAL_PRICE_KOP", raising=False)
    monkeypatch.delenv("LITTLE_LEGEND_PRINT_PRICE_KOP", raising=False)
    catalog = book_catalog()
    assert not catalog.checkout_enabled
    assert [offer.edition for offer in catalog.offers] == [
        BookEdition.DIGITAL, BookEdition.PRINT,
    ]
    assert all(not offer.available for offer in catalog.offers)
    with pytest.raises(PermissionError, match="price_not_configured"):
        quote_edition(BookEdition.DIGITAL)


def test_configured_digital_quote_uses_exact_integer_kopecks(monkeypatch):
    monkeypatch.setenv("LITTLE_LEGEND_DIGITAL_PRICE_KOP", "129900")
    monkeypatch.setenv("LITTLE_LEGEND_PRINT_PRICE_KOP", "299900")
    catalog = book_catalog()
    assert catalog.offers[0].price_minor == 129900
    assert catalog.offers[0].available
    assert not catalog.checkout_enabled
    assert not catalog.offers[1].available
    assert catalog.offers[1].reason == "print_production_not_certified"
    with pytest.raises(PermissionError, match="print_production_not_certified"):
        quote_edition(BookEdition.PRINT)


@pytest.mark.parametrize("value", ["0", "-100", "10.50", "1e5", "NaN", "１２３", "100000001"])
def test_invalid_price_fails_closed(monkeypatch, value):
    monkeypatch.setenv("LITTLE_LEGEND_DIGITAL_PRICE_KOP", value)
    with pytest.raises(ValueError, match="(?i)price"):
        book_catalog()
