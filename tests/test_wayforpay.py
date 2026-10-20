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

import hashlib
import hmac
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
        {"transactionStatus": "Approved", "authCode": "TEST-OK", "reasonCode": "1100"},
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
