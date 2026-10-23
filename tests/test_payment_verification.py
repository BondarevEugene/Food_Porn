"""A callback must not release files without a merchant-verified payment."""
from decimal import Decimal

import pytest

from app.config import Settings
from app.services import payment


class MockResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


@pytest.mark.asyncio
async def test_payment_matches_order_merchant_and_amount(monkeypatch):
    captured = []
    entries = [
        {"shopOrderNumber": "menu_17", "payee_id": "merchant",
         "billAmount": "499.00", "status": "PAYED", "payee_export_flag": "Y",
         "shopBillId": "p17"},
    ]

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json):
            captured.append((url, json))
            return MockResponse(entries)

    monkeypatch.setattr(payment.httpx, "AsyncClient", Client)
    settings = Settings(_env_file=None, portmone_payee_id="merchant", portmone_login="login",
                        portmone_password="secret", currency="UAH")
    service = payment.PaymentService(settings)
    assert (await service.verify_portmone_payment(17, Decimal("499"))).payment_id == "p17"
    assert captured[-1][1]["params"]["data"]["shopOrderNumber"] == "menu_17"

    # Menu and wallpaper orders have separate, non-interchangeable identities.
    entries[0]["shopOrderNumber"] = "wallpaper_17"
    assert (await service.verify_portmone_payment(17, Decimal("499"), product="wallpaper")).payment_id == "p17"
    assert await service.verify_portmone_payment(17, Decimal("499")) is None
    entries[0]["shopOrderNumber"] = "menu_17"

    for field, other in (("shopOrderNumber", "menu_18"), ("payee_id", "other"),
                         ("billAmount", "1.00"), ("status", "CREATED"),
                         ("payee_export_flag", "N")):
        original = entries[0][field]
        entries[0][field] = other
        assert await service.verify_portmone_payment(17, Decimal("499")) is None
        entries[0][field] = original


@pytest.mark.asyncio
async def test_unconfigured_payment_fails_closed():
    service = payment.PaymentService(Settings(_env_file=None))
    assert not service.portmone_ready
    with pytest.raises(payment.PaymentError):
        await service.verify_portmone_payment(5, Decimal("499"))
    assert not payment.PaymentService(Settings(_env_file=None, portmone_payee_id="merchant",
        portmone_login="login", portmone_password="secret", currency="USD")).portmone_ready


@pytest.mark.asyncio
async def test_mono_invoice_and_verification_are_order_bound(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, headers, json):
            captured["create"] = (url, headers, json)
            return MockResponse({"invoiceId": "mono-17", "pageUrl": "https://pay.mbnk.biz/test"})

        async def get(self, url, headers, params):
            captured["status"] = (url, headers, params)
            return MockResponse({
                "invoiceId": "mono-17",
                "status": "success",
                "amount": 49900,
                "ccy": 980,
                "reference": "menu_17",
            })

    monkeypatch.setattr(payment.httpx, "AsyncClient", Client)
    service = payment.PaymentService(
        Settings(_env_file=None, mono_token="merchant-token", currency="UAH")
    )
    invoice = await service.create_mono_invoice(17, Decimal("499"), "Digital menu")
    assert invoice.invoice_id == "mono-17"
    assert captured["create"][2]["amount"] == 49900
    assert captured["create"][2]["merchantPaymInfo"]["reference"] == "menu_17"
    verified = await service.verify_mono_payment(17, Decimal("499"), invoice.invoice_id)
    assert verified and verified.payment_id == "mono-17"
    assert captured["status"][2] == {"invoiceId": "mono-17"}


@pytest.mark.asyncio
async def test_mono_verification_rejects_wrong_amount(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, headers, params):
            return MockResponse({
                "invoiceId": "mono-17",
                "status": "success",
                "amount": 100,
                "ccy": 980,
                "reference": "menu_17",
            })

    monkeypatch.setattr(payment.httpx, "AsyncClient", Client)
    service = payment.PaymentService(Settings(_env_file=None, mono_token="token", currency="UAH"))
    assert await service.verify_mono_payment(17, Decimal("499"), "mono-17") is None
