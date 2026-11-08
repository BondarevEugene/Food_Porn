"""
==========================================================
FOOD_PORN

Module: WayForPay Payment Tests
Layer: Quality Assurance

Responsibilities:
    - Lock down signature order and exact amount matching
    - Verify sandbox configuration never requires a private production key
    - Verify the Telegram option coexists with another payment provider
==========================================================
"""

from __future__ import annotations

import ast
import hashlib
import hmac
import inspect
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.bot.keyboards import add_wayforpay_option, get_payment_keyboard
from app.config import Settings
from app.services.wayforpay import (
    TEST_MERCHANT_ACCOUNT,
    TEST_MERCHANT_SECRET,
    WayForPayError,
    WayForPayService,
    apply_verified_payment,
)


def sign(values: list[str]) -> str:
    source = ";".join(values)
    return hmac.new(
        TEST_MERCHANT_SECRET.encode(), source.encode(), hashlib.md5
    ).hexdigest()


def settings(**kwargs) -> Settings:
    values = {
        "public_base_url": "https://foodporn-production.up.railway.app",
        "wayforpay_merchant_domain": "foodporn-production.up.railway.app",
        "wayforpay_test_mode": True,
        **kwargs,
    }
    return Settings(_env_file=None, **values)


def payment(**kwargs):
    data = {
        "id": 7,
        "order_reference": "fp_menu_17_abcdef",
        "checkout_token": "safe-token",
        "amount": Decimal("5.00"),
        "currency": "UAH",
        "description": "Food Porn digital menu #17",
        "created_at": datetime(2026, 10, 20, 10, 0, tzinfo=UTC),
        "test_mode": True,
        "grants_entitlement": True,
        "status": "pending",
        "paid_at": None,
        "provider_payment_id": None,
        "error_message": None,
        "transaction_status": None,
        "reason_code": None,
        "provider_payload": None,
        "product": "menu",
        "reference_id": "17",
        "telegram_user_id": 12345,
        "payment_id": None,
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_sandbox_is_ready_with_public_test_merchant() -> None:
    service = WayForPayService(settings())
    credentials = service.credentials()
    assert service.ready
    assert credentials.account == TEST_MERCHANT_ACCOUNT
    assert credentials.domain == "foodporn-production.up.railway.app"
    assert service.price_for("menu") == Decimal("5.00")
    assert service.price_for("wallpaper") == Decimal("1.00")


def test_production_requires_real_merchant_credentials() -> None:
    service = WayForPayService(settings(wayforpay_test_mode=False))
    assert not service.ready
    with pytest.raises(WayForPayError, match="credentials"):
        service.credentials()


def test_purchase_form_has_exact_signature_and_server_urls() -> None:
    service = WayForPayService(settings())
    fields = service.form_fields(payment())
    expected = sign([
        TEST_MERCHANT_ACCOUNT,
        "foodporn-production.up.railway.app",
        "fp_menu_17_abcdef",
        "1792490400",
        "5.00",
        "UAH",
        "Food Porn digital menu #17",
        "1",
        "5.00",
    ])
    assert fields["merchantSignature"] == expected
    assert fields["amount"] == "5.00"
    assert fields["serviceUrl"] == (
        "https://foodporn-production.up.railway.app/payments/wayforpay/webhook"
    )
    assert fields["returnUrl"].endswith("/payments/wayforpay/return")


def test_callback_requires_signature_order_amount_currency_and_order() -> None:
    service = WayForPayService(settings())
    attempt = payment()
    payload = {
        "merchantAccount": TEST_MERCHANT_ACCOUNT,
        "orderReference": attempt.order_reference,
        "amount": "5.00",
        "currency": "UAH",
        "authCode": "TEST-OK",
        "cardPan": "411111****1111",
        "transactionStatus": "Approved",
        "reasonCode": "1100",
    }
    payload["merchantSignature"] = sign([
        payload[key] for key in (
            "merchantAccount", "orderReference", "amount", "currency", "authCode",
            "cardPan", "transactionStatus", "reasonCode",
        )
    ])
    assert service.verify_provider_payload(attempt, payload)
    payload["amount"] = "1.00"
    assert not service.verify_provider_payload(attempt, payload)


@pytest.mark.asyncio
async def test_vip_test_payment_is_recorded_without_changing_entitlement() -> None:
    attempt = payment(grants_entitlement=False)
    session = SimpleNamespace(commit=AsyncMock())

    assert await apply_verified_payment(
        session,
        attempt,
        {
            "transactionStatus": "Approved",
            "authCode": "TEST-OK",
            "reasonCode": "1100",
        },
    )

    assert attempt.status == "approved"
    session.commit.assert_awaited_once()


def test_wayforpay_button_is_added_without_removing_existing_checkout() -> None:
    original = get_payment_keyboard(
        17, "https://pay.mbnk.biz/test", "ru", provider="mono", amount="500.00"
    )
    result = add_wayforpay_option(
        original,
        product="menu",
        reference_id=17,
        payment_id=7,
        checkout_url="https://foodporn-production.up.railway.app/payments/wayforpay/checkout/token",
        amount="5.00",
        language="ru",
        test_mode=True,
    )
    urls = [button.url for row in result.inline_keyboard for button in row if button.url]
    callbacks = [
        button.callback_data
        for row in result.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "https://pay.mbnk.biz/test" in urls
    assert any("/payments/wayforpay/checkout/" in url for url in urls)
    assert "check_wayforpay:7" in callbacks


def test_menu_pipeline_passes_only_supported_wayforpay_arguments() -> None:
    """Prevent silent button loss caused by an invalid checkout keyword."""
    source_path = Path(__file__).parents[1] / "app" / "workers" / "menu_pipeline.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    supported = set(inspect.signature(WayForPayService.create_checkout).parameters)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "wayforpay"
        and node.func.attr == "create_checkout"
    ]
    assert calls
    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords if keyword.arg}
        assert keywords <= supported

@pytest.mark.asyncio
async def test_wayforpay_grants_unpaid_menu_once() -> None:
    menu = SimpleNamespace(
        is_paid=False,
        payment_system=None,
        payment_id=None,
        customer=SimpleNamespace(telegram_user_id=12345),
        price_amount=None,
        paid_at=None,
        status="waiting_for_payment",
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=menu),
        refresh=AsyncMock(),
        commit=AsyncMock(),
    )
    attempt = payment()

    result = await apply_verified_payment(
        session,
        attempt,
        {
            "transactionStatus": "Approved",
            "authCode": "WFP-001",
            "reasonCode": "1100",
        },
    )

    assert result is True
    assert menu.is_paid is True
    assert menu.payment_system == "wayforpay"
    assert menu.payment_id == attempt.order_reference
    assert attempt.status == "approved"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_wayforpay_does_not_override_stars_menu_payment() -> None:
    menu = SimpleNamespace(
        is_paid=True,
        payment_system="telegram_stars",
        payment_id="STARS-001",
        customer=SimpleNamespace(telegram_user_id=12345),
        price_amount=None,
        paid_at=None,
        status="paid",
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=menu),
        refresh=AsyncMock(),
        commit=AsyncMock(),
    )
    attempt = payment()

    result = await apply_verified_payment(
        session,
        attempt,
        {
            "transactionStatus": "Approved",
            "authCode": "WFP-002",
            "reasonCode": "1100",
        },
    )

    assert result is False
    assert attempt.status == "approved"
    assert menu.payment_system == "telegram_stars"
    assert menu.payment_id == "STARS-001"
    assert attempt.error_message is not None
    assert "duplicate_payment" in attempt.error_message
    assert "telegram_stars" in attempt.error_message
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_wayforpay_same_attempt_is_idempotent() -> None:
    attempt = payment()

    menu = SimpleNamespace(
        is_paid=True,
        payment_system="wayforpay",
        payment_id=attempt.order_reference,
        customer=SimpleNamespace(telegram_user_id=12345),
        price_amount=attempt.amount,
        paid_at=datetime.now(UTC),
        status="paid",
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=menu),
        refresh=AsyncMock(),
        commit=AsyncMock(),
    )

    result = await apply_verified_payment(
        session,
        attempt,
        {
            "transactionStatus": "Approved",
            "authCode": "WFP-001",
            "reasonCode": "1100",
        },
    )
    assert attempt.error_message is None
    assert result is True
    assert menu.payment_id == attempt.order_reference
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_wayforpay_rejects_unknown_product() -> None:
    attempt = payment(product="unknown")
    session = SimpleNamespace(commit=AsyncMock())

    with pytest.raises(WayForPayError, match="Unsupported"):
        await apply_verified_payment(
            session,
            attempt,
            {"transactionStatus": "Approved"},
        )

    assert attempt.status == "pending"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_wayforpay_does_not_override_stars_wallpaper_payment() -> None:
    attempt = payment(product="wallpaper", reference_id="29")

    order = SimpleNamespace(
        paid=True,
        payment_system="telegram_stars",
        payment_id="STARS-002",
        telegram_user_id=12345,
        amount=Decimal("1.00"),
        paid_at=datetime.now(UTC),
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=order),
        commit=AsyncMock(),
    )

    result = await apply_verified_payment(
        session,
        attempt,
        {
            "transactionStatus": "Approved",
            "authCode": "WFP-003",
            "reasonCode": "1100",
        },
    )

    assert result is False
    assert attempt.status == "approved"
    assert order.payment_system == "telegram_stars"
    assert order.payment_id == "STARS-002"
    assert attempt.error_message is not None
    assert "duplicate_payment" in attempt.error_message
    assert "telegram_stars" in attempt.error_message
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_owns_order", "expected_delivery", "expected_alert"),
    [
        (True, True, False),
        (False, False, True),
    ],
)
async def test_wayforpay_new_approved_payment_delivery(
    monkeypatch, provider_owns_order, expected_delivery, expected_alert
) -> None:
    """Перевірка нової оплати: доставка лише власнику замовлення."""
    from app.bot.handlers import wayforpay as handler

    attempt = payment()
    callback = SimpleNamespace(
        data="check_wayforpay:7",
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    session = SimpleNamespace()
    factory = Mock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(
        handler.WayForPayPaymentRepository,
        "get_for_user",
        AsyncMock(return_value=attempt),
    )
    monkeypatch.setattr(
        handler.WayForPayService, "check_status",
        AsyncMock(return_value={"transactionStatus": "Approved"}),
    )

    async def approve(session_arg, payment_arg, payload):
        payment_arg.status = "approved"
        return provider_owns_order

    monkeypatch.setattr(handler, "apply_verified_payment", approve)
    deliver = AsyncMock(return_value=True)
    monkeypatch.setattr(handler, "_deliver_menu", deliver)

    await handler.check_wayforpay(callback, settings(), factory)

    assert deliver.await_count == int(expected_delivery)
    assert callback.answer.await_args.kwargs.get("show_alert", False) == expected_alert


@pytest.mark.asyncio
async def test_wayforpay_repeated_approval_checks_entitlement(monkeypatch) -> None:
    """Повторний запит не повинен видавати файли чужої спроби оплати."""
    from app.bot.handlers import wayforpay as handler

    attempt = payment(status="approved")
    callback = SimpleNamespace(
        data="check_wayforpay:7",
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    factory = Mock()
    factory.return_value.__aenter__ = AsyncMock(return_value=SimpleNamespace())
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(
        handler.WayForPayPaymentRepository,
        "get_for_user",
        AsyncMock(return_value=attempt),
    )
    entitlement = AsyncMock(return_value=False)
    deliver = AsyncMock(return_value=True)
    monkeypatch.setattr(handler, "wayforpay_entitlement_is_active", entitlement)
    monkeypatch.setattr(handler, "_deliver_menu", deliver)

    await handler.check_wayforpay(callback, settings(), factory)

    entitlement.assert_awaited_once()
    deliver.assert_not_awaited()
    assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_wayforpay_missing_files_reports_delivery_failure(monkeypatch) -> None:
    """Підтверджена оплата без готових файлів не вважається доставкою."""
    from app.bot.handlers import wayforpay as handler

    attempt = payment(status="approved")
    callback = SimpleNamespace(
        data="check_wayforpay:7",
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    factory = Mock()
    factory.return_value.__aenter__ = AsyncMock(return_value=SimpleNamespace())
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(
        handler.WayForPayPaymentRepository,
        "get_for_user",
        AsyncMock(return_value=attempt),
    )
    monkeypatch.setattr(
        handler, "wayforpay_entitlement_is_active", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(handler, "_deliver_menu", AsyncMock(return_value=False))

    await handler.check_wayforpay(callback, settings(), factory)

    assert callback.answer.await_args.kwargs["show_alert"] is True
    assert "файли" in callback.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_wayforpay_telegram_delivery_failure_can_retry(monkeypatch) -> None:
    """Помилка Telegram не скасовує оплату; повторний запит доставляє файли."""
    from aiogram.exceptions import TelegramNetworkError

    from app.bot.handlers import wayforpay as handler

    attempt = payment(status="approved")
    callback = SimpleNamespace(
        data="check_wayforpay:7",
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    factory = Mock()
    factory.return_value.__aenter__ = AsyncMock(return_value=SimpleNamespace())
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(
        handler.WayForPayPaymentRepository,
        "get_for_user",
        AsyncMock(return_value=attempt),
    )
    entitlement = AsyncMock(return_value=True)
    monkeypatch.setattr(handler, "wayforpay_entitlement_is_active", entitlement)
    deliver = AsyncMock(
        side_effect=[
            TelegramNetworkError(method=Mock(), message="Temporary network failure"),
            True,
        ]
    )
    monkeypatch.setattr(handler, "_deliver_menu", deliver)

    await handler.check_wayforpay(callback, settings(), factory)
    assert attempt.status == "approved"
    assert callback.answer.await_args.kwargs["show_alert"] is True
    assert "Повторіть" in callback.answer.await_args.args[0]

    callback.answer.reset_mock()
    await handler.check_wayforpay(callback, settings(), factory)
    assert attempt.status == "approved"
    assert deliver.await_count == 2
    assert entitlement.await_count == 2
    assert callback.answer.await_args.kwargs.get("show_alert", False) is False


@pytest.mark.asyncio
async def test_wayforpay_second_menu_document_failure_is_retryable(
    monkeypatch, tmp_path
) -> None:
    """Часткова доставка не змінює оплату та дозволяє повторну відправку."""
    from aiogram.exceptions import TelegramNetworkError

    from app.bot.handlers import wayforpay as handler
    from app.database.models import FileKind

    pdf = tmp_path / "menu.pdf"
    recipe = tmp_path / "recipe.pdf"
    pdf.write_bytes(b"pdf")
    recipe.write_bytes(b"recipe")
    menu = SimpleNamespace(
        is_paid=True,
        customer=SimpleNamespace(telegram_user_id=12345),
        files=[
            SimpleNamespace(kind=FileKind.PRINT_PDF, path=str(pdf)),
            SimpleNamespace(kind=FileKind.RECIPE_SHEET, path=str(recipe)),
        ],
    )
    monkeypatch.setattr(
        handler.MenuRepository, "get", AsyncMock(return_value=menu)
    )
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(
            answer_document=AsyncMock(
                side_effect=[
                    None,
                    TelegramNetworkError(method=Mock(), message="Temporary network failure"),
                    None,
                    None,
                ]
            )
        ),
    )
    with pytest.raises(TelegramNetworkError):
        await handler._deliver_menu(callback, 17, SimpleNamespace())

    assert menu.is_paid is True
    assert await handler._deliver_menu(callback, 17, SimpleNamespace()) is True
    assert callback.message.answer_document.await_count == 4


@pytest.mark.asyncio
async def test_wayforpay_repeated_approved_webhook_keeps_original_entitlement() -> None:
    """Повторне підтвердження не змінює власника та ідентифікатор оплати."""
    attempt = payment()
    menu = SimpleNamespace(
        is_paid=False,
        payment_system=None,
        payment_id=None,
        customer=SimpleNamespace(telegram_user_id=12345),
        price_amount=None,
        paid_at=None,
        status="waiting_for_payment",
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=menu),
        refresh=AsyncMock(),
        commit=AsyncMock(),
    )
    payload = {
        "transactionStatus": "Approved",
        "authCode": "WFP-REPEAT-001",
        "reasonCode": "1100",
    }

    assert await apply_verified_payment(session, attempt, payload) is True
    first_paid_at = attempt.paid_at
    first_order_paid_at = menu.paid_at
    assert await apply_verified_payment(session, attempt, payload) is True

    assert attempt.status == "approved"
    assert attempt.paid_at == first_paid_at
    assert menu.paid_at == first_order_paid_at
    assert menu.payment_system == "wayforpay"
    assert menu.payment_id == attempt.order_reference
    assert attempt.error_message is None
    assert session.commit.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("product", ["menu", "wallpaper"])
async def test_wayforpay_two_approved_attempts_preserve_first_owner(product) -> None:
    """Друга підтверджена транзакція зберігається для фінансової звірки."""
    first = payment(product=product, reference_id="17")
    second = payment(
        id=8,
        product=product,
        reference_id="17",
        order_reference="fp_second_17_abcdef",
    )
    if product == "menu":
        order = SimpleNamespace(
            is_paid=False,
            payment_system=None,
            payment_id=None,
            customer=SimpleNamespace(telegram_user_id=12345),
            price_amount=None,
            paid_at=None,
            status="waiting_for_payment",
        )
    else:
        order = SimpleNamespace(
            paid=False,
            payment_system=None,
            payment_id=None,
            telegram_user_id=12345,
            amount=None,
            paid_at=None,
        )
    session = SimpleNamespace(
        get=AsyncMock(return_value=order),
        refresh=AsyncMock(),
        commit=AsyncMock(),
    )
    payload = {"transactionStatus": "Approved", "authCode": "WFP-DUPLICATE"}

    assert await apply_verified_payment(session, first, payload) is True
    assert await apply_verified_payment(session, second, payload) is False
    assert first.status == "approved"
    assert second.status == "approved"
    assert order.payment_system == "wayforpay"
    assert order.payment_id == first.order_reference
    assert "duplicate_payment" in second.error_message
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_wayforpay_late_failed_notification_does_not_revoke_approval() -> None:
    """Запізніле негативне повідомлення не скасовує підтверджений платіж."""
    attempt = payment(status="approved")
    session = SimpleNamespace(commit=AsyncMock())
    result = await apply_verified_payment(
        session,
        attempt,
        {"transactionStatus": "Declined", "reasonCode": "1101"},
    )
    assert result is False
    assert attempt.status == "approved"
    session.commit.assert_awaited_once()
