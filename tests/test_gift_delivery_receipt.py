"""Safety checks for delivery of a paid two-product gift."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.gift_delivery import deliver_paid_gift


class Session:
    def __init__(self, objects):
        self.objects = objects

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, model, key, **kwargs):
        return self.objects.get(model.__name__)


@pytest.mark.asyncio
@pytest.mark.parametrize("receipt_amount,receipt_currency,provider", [
    (Decimal("399.00"), "UAH", "wayforpay"),
    (Decimal("400.00"), "USD", "wayforpay"),
    (Decimal("400.00"), "UAH", "unknown"),
])
async def test_delivery_refuses_mismatched_receipt(
    receipt_amount, receipt_currency, provider,
):
    purchase = SimpleNamespace(status="paid", total_amount=Decimal("400.00"), currency="UAH")
    receipt = SimpleNamespace(amount=receipt_amount, currency=receipt_currency, provider=provider)
    job = SimpleNamespace(status="ready")
    objects = {
        "GiftPurchase": purchase,
        "GiftPaymentReceipt": receipt,
        "GiftFulfillment": job,
    }
    bot = SimpleNamespace(send_media_group=AsyncMock(), send_video=AsyncMock())
    with pytest.raises(ValueError, match="Verified gift purchase"):
        await deliver_paid_gift(lambda: Session(objects), bot, "purchase-id")
    bot.send_media_group.assert_not_awaited()
    bot.send_video.assert_not_awaited()
    assert job.status == "ready"


@pytest.mark.asyncio
async def test_completed_delivery_does_not_resend_assets():
    objects = {
        "GiftPurchase": SimpleNamespace(status="paid", total_amount=Decimal("400.00"), currency="UAH"),
        "GiftPaymentReceipt": SimpleNamespace(
            amount=Decimal("400.00"), currency="UAH", provider="wayforpay",
        ),
        "GiftFulfillment": SimpleNamespace(status="delivered"),
    }
    bot = SimpleNamespace(send_media_group=AsyncMock(), send_video=AsyncMock())
    assert await deliver_paid_gift(lambda: Session(objects), bot, "purchase-id") is False
    bot.send_media_group.assert_not_awaited()
    bot.send_video.assert_not_awaited()
