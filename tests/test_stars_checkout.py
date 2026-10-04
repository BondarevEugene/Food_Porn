"""Star invoice and receipt validation without external payments."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import stars as handlers
from app.services.stars import OrderRef, create_invoice, parse_payload


def test_payload_cannot_switch_order_owner_or_amount() -> None:
    ref = OrderRef("menu", 45, 725003786, 41)
    assert parse_payload(ref.payload) == ref
    for value in ("fp:menu:45:725003786:0", "fp:gift:45:725003786:41",
                  "fp:menu:45:725003786:041", "fp:menu:45:other:41"):
        assert parse_payload(value) is None


@pytest.mark.asyncio
async def test_invoice_has_one_star_price_and_no_portmone_token() -> None:
    bot = SimpleNamespace(create_invoice_link=AsyncMock(return_value="https://t.me/$invoice"))
    ref = OrderRef("wallpaper", 12, 42, 17)
    assert await create_invoice(bot, ref) == "https://t.me/$invoice"
    options = bot.create_invoice_link.await_args.kwargs
    assert options["currency"] == "XTR" and options["payload"] == ref.payload
    assert len(options["prices"]) == 1 and options["prices"][0].amount == 17
    assert "provider_token" not in options


@pytest.mark.asyncio
async def test_precheckout_rejects_foreign_user_or_changed_price(monkeypatch) -> None:
    async def available(*args):
        return True
    monkeypatch.setattr(handlers, "payment_is_available", available)
    ref = OrderRef("menu", 5, 42, 20)
    query = SimpleNamespace(invoice_payload=ref.payload, currency="XTR", total_amount=20,
                            from_user=SimpleNamespace(id=99), answer=AsyncMock())
    await handlers.stars_pre_checkout(query)
    assert query.answer.await_args.kwargs["ok"] is False
    query.from_user.id = 42
    query.total_amount = 19
    await handlers.stars_pre_checkout(query)
    assert query.answer.await_args.kwargs["ok"] is False
    query.total_amount = 20
    await handlers.stars_pre_checkout(query)
    assert query.answer.await_args.kwargs["ok"] is True


@pytest.mark.asyncio
async def test_duplicate_charge_is_refunded(monkeypatch) -> None:
    async def already_paid(*args):
        return "duplicate"
    monkeypatch.setattr(handlers, "record_payment", already_paid)
    ref = OrderRef("menu", 45, 42, 30)
    bot = SimpleNamespace(refund_star_payment=AsyncMock())
    message = SimpleNamespace(message_id=1, from_user=SimpleNamespace(id=42), bot=bot,
                              successful_payment=SimpleNamespace(invoice_payload=ref.payload,
                                  currency="XTR", total_amount=30,
                                  telegram_payment_charge_id="charge-2"), answer=AsyncMock())
    await handlers.stars_success(message)
    bot.refund_star_payment.assert_awaited_once_with(42, "charge-2")
