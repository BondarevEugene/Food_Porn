"""Перевірки HTTP webhook WayForPay без звернення до робочої бази."""

from __future__ import annotations

import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.api import wayforpay as api
from app.services.wayforpay import TEST_MERCHANT_ACCOUNT, TEST_MERCHANT_SECRET
from tests.test_wayforpay import payment, settings


def _signed_payload(attempt):
    payload = {
        "merchantAccount": TEST_MERCHANT_ACCOUNT,
        "orderReference": attempt.order_reference,
        "amount": "5.00",
        "currency": "UAH",
        "authCode": "AUTH-OK",
        "cardPan": "411111****1111",
        "transactionStatus": "Approved",
        "reasonCode": "1100",
    }
    values = [
        payload[key]
        for key in (
            "merchantAccount",
            "orderReference",
            "amount",
            "currency",
            "authCode",
            "cardPan",
            "transactionStatus",
            "reasonCode",
        )
    ]
    payload["merchantSignature"] = hmac.new(
        TEST_MERCHANT_SECRET.encode(),
        ";".join(values).encode(),
        hashlib.md5,
    ).hexdigest()
    return payload


def _session_factory():
    factory = Mock()
    factory.return_value.__aenter__ = AsyncMock(return_value=SimpleNamespace())
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


@pytest.mark.asyncio
async def test_webhook_rejects_missing_reference(monkeypatch):
    monkeypatch.setattr(api, "_payload", AsyncMock(return_value={}))
    with pytest.raises(HTTPException) as exc:
        await api.webhook(SimpleNamespace())
    assert exc.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["signature", "amount", "currency"])
async def test_webhook_rejects_invalid_signed_data(monkeypatch, mutation):
    attempt = payment()
    payload = _signed_payload(attempt)
    if mutation == "signature":
        payload["merchantSignature"] = "0" * 32
    elif mutation == "amount":
        payload["amount"] = "99.00"
    else:
        payload["currency"] = "USD"
    apply = AsyncMock()
    monkeypatch.setattr(api, "_payload", AsyncMock(return_value=payload))
    monkeypatch.setattr(api, "get_settings", lambda: settings())
    monkeypatch.setattr(api, "async_session_maker", _session_factory())
    monkeypatch.setattr(
        api.WayForPayPaymentRepository,
        "by_order_reference",
        AsyncMock(return_value=attempt),
    )
    monkeypatch.setattr(api, "apply_verified_payment", apply)

    with pytest.raises(HTTPException) as exc:
        await api.webhook(SimpleNamespace())

    assert exc.value.status_code == 400
    apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_rejects_unknown_reference(monkeypatch):
    attempt = payment()
    monkeypatch.setattr(api, "_payload", AsyncMock(return_value=_signed_payload(attempt)))
    monkeypatch.setattr(api, "get_settings", lambda: settings())
    monkeypatch.setattr(api, "async_session_maker", _session_factory())
    monkeypatch.setattr(
        api.WayForPayPaymentRepository,
        "by_order_reference",
        AsyncMock(return_value=None),
    )
    apply = AsyncMock()
    monkeypatch.setattr(api, "apply_verified_payment", apply)
    with pytest.raises(HTTPException) as exc:
        await api.webhook(SimpleNamespace())
    assert exc.value.status_code == 400
    apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_repeated_signed_callback_is_acknowledged(monkeypatch):
    attempt = payment()
    payload = _signed_payload(attempt)
    monkeypatch.setattr(api, "_payload", AsyncMock(return_value=payload))
    monkeypatch.setattr(api, "get_settings", lambda: settings())
    monkeypatch.setattr(api, "async_session_maker", _session_factory())
    lookup = AsyncMock(return_value=attempt)
    monkeypatch.setattr(api.WayForPayPaymentRepository, "by_order_reference", lookup)
    apply = AsyncMock(return_value=True)
    monkeypatch.setattr(api, "apply_verified_payment", apply)

    first = await api.webhook(SimpleNamespace())
    second = await api.webhook(SimpleNamespace())

    assert first.status_code == 200
    assert second.status_code == 200
    assert apply.await_count == 2
    assert lookup.await_count == 2
    assert all(call.kwargs.get("lock") is True for call in lookup.await_args_list)


@pytest.mark.asyncio
async def test_webhook_returns_conflict_for_invalid_order_state(monkeypatch):
    from app.services.wayforpay import WayForPayError

    attempt = payment()
    monkeypatch.setattr(api, "_payload", AsyncMock(return_value=_signed_payload(attempt)))
    monkeypatch.setattr(api, "get_settings", lambda: settings())
    monkeypatch.setattr(api, "async_session_maker", _session_factory())
    monkeypatch.setattr(
        api.WayForPayPaymentRepository,
        "by_order_reference",
        AsyncMock(return_value=attempt),
    )
    monkeypatch.setattr(
        api,
        "apply_verified_payment",
        AsyncMock(side_effect=WayForPayError("Payment owner mismatch")),
    )
    with pytest.raises(HTTPException) as exc:
        await api.webhook(SimpleNamespace())
    assert exc.value.status_code == 409
