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
