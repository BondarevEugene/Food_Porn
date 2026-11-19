"""Order quote contract must never authorize payments or printing."""
import pytest
from pydantic import ValidationError

from app.little_legend.commercial_catalog import BookEdition
from app.little_legend.order_quotes import BookOrderQuote, create_order_quote


def test_quote_is_never_payment_or_production_entitlement():
    from datetime import UTC, datetime

    quote = BookOrderQuote(
        id=1, owner_id=123, story_id=456, edition=BookEdition.DIGITAL,
        price_minor=129900, created_at=datetime.now(UTC),
    )
    assert quote.status == "quoted"
    assert not quote.payment_enabled
    assert not quote.production_enabled


def test_quote_rejects_zero_price():
    from datetime import UTC, datetime

    with pytest.raises(ValidationError):
        BookOrderQuote(
            id=1, owner_id=123, story_id=456, edition=BookEdition.DIGITAL,
            price_minor=0, created_at=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_print_cannot_be_quoted():
    with pytest.raises(PermissionError, match="print_production_not_certified"):
        await create_order_quote(owner_id=123, story_id=456, edition=BookEdition.PRINT)
