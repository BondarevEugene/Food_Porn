"""
==========================================================
FOOD_PORN

Module: Portmone Sandbox Tests
Layer: Test Suite
==========================================================

Portmone sandbox must be explicit, isolated and unable to unlock products.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import portmone_sandbox
from app.config import Settings
from app.services import portmone_sandbox as offers


class SessionFactory:
    def __init__(self, session=None):
        self.session = session or SimpleNamespace()

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_offer_is_hidden_until_test_mode_and_credentials_are_ready(monkeypatch) -> None:
    bot = SimpleNamespace(send_message=AsyncMock())
    factory = SessionFactory()
    settings = Settings(_env_file=None, portmone_test_mode=False)
    assert not await offers.send_portmone_sandbox_offer(
        bot=bot,
        settings=settings,
        session_factory=factory,
        telegram_user_id=42,
        product="menu",
        reference_id="7",
        language="ru",
    )
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_offer_creates_separate_sandbox_order(monkeypatch) -> None:
    payment = SimpleNamespace(id=9)
    repository = SimpleNamespace(create=AsyncMock(return_value=payment), mark_failed=AsyncMock())
    monkeypatch.setattr(offers, "PortmoneSandboxPaymentRepository", lambda _session: repository)
    create_invoice = AsyncMock(return_value="https://www.portmone.com.ua/r3/uk/i/test")
    monkeypatch.setattr(
        offers,
        "PaymentService",
        lambda _settings: SimpleNamespace(portmone_ready=True, create_portmone_invoice=create_invoice),
    )
    bot = SimpleNamespace(send_message=AsyncMock())
    settings = Settings(
        _env_file=None,
        portmone_test_mode=True,
        portmone_test_amount_uah=Decimal("1.00"),
    )
    assert await offers.send_portmone_sandbox_offer(
        bot=bot,
        settings=settings,
        session_factory=SessionFactory(),
        telegram_user_id=42,
        product="wallpaper",
        reference_id="job-1",
        language="ru",
    )
    assert repository.create.await_args.kwargs == {
        "telegram_user_id": 42,
        "product": "wallpaper",
        "reference_id": "job-1",
        "amount": Decimal("1.00"),
    }
    assert create_invoice.await_args.kwargs["product"] == "sandbox_wallpaper"
    message = bot.send_message.await_args.kwargs
    assert "Это не покупка" in message["text"]
    assert message["reply_markup"].inline_keyboard[1][0].callback_data == "portmone_test_check:9"


@pytest.mark.asyncio
async def test_offer_failure_never_breaks_vip_delivery(monkeypatch) -> None:
    repository = SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("database unavailable")))
    monkeypatch.setattr(offers, "PortmoneSandboxPaymentRepository", lambda _session: repository)
    monkeypatch.setattr(
        offers,
        "PaymentService",
        lambda _settings: SimpleNamespace(portmone_ready=True),
    )
    bot = SimpleNamespace(send_message=AsyncMock())
    settings = Settings(_env_file=None, portmone_test_mode=True)
    assert not await offers.send_portmone_sandbox_offer(
        bot=bot,
        settings=settings,
        session_factory=SessionFactory(),
        telegram_user_id=42,
        product="menu",
        reference_id="7",
        language="ru",
    )
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_denies_non_vip_before_database_lookup(monkeypatch) -> None:
    monkeypatch.setattr(portmone_sandbox, "has_free_generation_access", AsyncMock(return_value=False))
    callback = SimpleNamespace(
        data="portmone_test_check:9",
        from_user=SimpleNamespace(id=42, username="stranger"),
        answer=AsyncMock(),
    )
    settings = Settings(_env_file=None, portmone_test_mode=True)
    await portmone_sandbox.verify_portmone_sandbox(
        callback,
        settings,
        SessionFactory(),
    )
    assert callback.answer.await_args.kwargs["show_alert"] is True
    assert "недоступен" in callback.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_callback_records_only_sandbox_result(monkeypatch) -> None:
    payment = SimpleNamespace(
        id=9,
        amount=Decimal("1.00"),
        product="menu",
        status="pending",
    )
    repository = SimpleNamespace(
        get_for_user=AsyncMock(return_value=payment),
        mark_paid=AsyncMock(),
    )
    monkeypatch.setattr(
        portmone_sandbox,
        "PortmoneSandboxPaymentRepository",
        lambda _session: repository,
    )
    monkeypatch.setattr(
        portmone_sandbox,
        "has_free_generation_access",
        AsyncMock(return_value=True),
    )
    verify = AsyncMock(return_value=SimpleNamespace(payment_id="shop-bill-9"))
    monkeypatch.setattr(
        portmone_sandbox,
        "PaymentService",
        lambda _settings: SimpleNamespace(verify_portmone_payment=verify),
    )
    callback = SimpleNamespace(
        data="portmone_test_check:9",
        from_user=SimpleNamespace(id=42, username="vip"),
        answer=AsyncMock(),
    )
    settings = Settings(_env_file=None, portmone_test_mode=True)
    await portmone_sandbox.verify_portmone_sandbox(
        callback,
        settings,
        SessionFactory(),
    )
    verify.assert_awaited_once_with(9, Decimal("1.00"), product="sandbox_menu")
    repository.mark_paid.assert_awaited_once_with(payment, "shop-bill-9")
    assert "Тест Portmone пройден" in callback.answer.await_args.args[0]


def test_sandbox_products_have_distinct_provider_order_numbers() -> None:
    from app.services.payment import PaymentService

    assert PaymentService._order_number(3, "sandbox_menu") == "sandbox_menu_3"
    assert PaymentService._order_number(3, "sandbox_wallpaper") == "sandbox_wallpaper_3"
