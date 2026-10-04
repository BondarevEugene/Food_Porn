"""Portmone checkout and server-side payment verification.

API: https://docs.portmone.com.ua/en/docs/en/PaymentGatewayEng/
Sections 12.4 (getLinkInvoice) and 8.2.2 (authorization results).
Never trust a redirect or Telegram callback as proof of payment.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)
LINK_API = "https://www.portmone.com.ua/r3/api/gateway/"
STATUS_API = "https://www.portmone.com.ua/gateway/"


class PaymentError(RuntimeError):
    """Payment could not be safely initiated or verified."""


@dataclass(frozen=True)
class VerifiedPayment:
    payment_id: str
    order_number: str
    amount: Decimal


class PaymentService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def portmone_ready(self) -> bool:
        return self.settings.currency == "UAH" and all(
            value and value != "replace_me"
            for value in (
                self.settings.portmone_payee_id,
                self.settings.portmone_login,
                self.settings.portmone_password.get_secret_value(),
            )
        )

    def _credentials(self) -> dict[str, str]:
        if not self.portmone_ready:
            raise PaymentError("Portmone merchant credentials are not configured")
        return {
            "login": self.settings.portmone_login,
            "password": self.settings.portmone_password.get_secret_value(),
            "payeeId": self.settings.portmone_payee_id,
        }

    @staticmethod
    def _order_number(order_id: int, product: str = "menu") -> str:
        if order_id <= 0 or product not in {"menu", "wallpaper"}:
            raise ValueError("Invalid payment order")
        return f"{product}_{order_id}"

    async def create_portmone_invoice(self, menu_id: int, amount: float, description: str,
                                      product: str = "menu") -> str:
        """Ask Portmone to issue a real, order-specific checkout link."""
        if self.settings.currency != "UAH":
            raise PaymentError("Portmone checkout currently supports UAH only")
        money = Decimal(str(amount)).quantize(Decimal("0.01"))
        if money <= 0:
            raise PaymentError("Payment amount must be positive")
        payload = {
            "method": "getLinkInvoice",
            "params": {"data": {
                **self._credentials(),
                "amount": str(money),
                "billCurrency": "UAH",
                "shopOrderNumber": self._order_number(menu_id, product),
                "comment": description[:250],
                "preauthFlag": "N",
            }},
            "id": str(menu_id),
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(LINK_API, json=payload)
            response.raise_for_status()
        try:
            data = response.json()
            link = data["result"]["linkInvoice"]
        except (ValueError, KeyError, TypeError) as exc:
            raise PaymentError("Portmone did not return a checkout link") from exc
        parsed = urlparse(str(link))
        if parsed.scheme != "https" or parsed.hostname not in {"www.portmone.com.ua", "portmone.com.ua"}:
            raise PaymentError("Portmone returned an unexpected checkout URL")
        return str(link)

    async def verify_portmone_payment(self, menu_id: int, expected_amount: float,
                                      product: str = "menu") -> VerifiedPayment | None:
        """Return a payment only after matching merchant, order, amount and final status."""
        order_number = self._order_number(menu_id, product)
        payload = {
            "method": "result",
            "params": {"data": {
                **self._credentials(),
                "shopOrderNumber": order_number,
                "status": "PAYED",
            }},
            "id": str(menu_id),
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(STATUS_API, json=payload)
            response.raise_for_status()
        try:
            entries = response.json()
        except ValueError as exc:
            raise PaymentError("Portmone returned an invalid status response") from exc
        if not isinstance(entries, list):
            raise PaymentError("Portmone status response has an unexpected structure")
        expected = Decimal(str(expected_amount)).quantize(Decimal("0.01"))
        for item in entries:
            if not isinstance(item, dict):
                continue
            try:
                amount = Decimal(str(item["billAmount"])).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError, KeyError):
                continue
            if (
                item.get("shopOrderNumber") == order_number
                and str(item.get("payee_id", item.get("payeeId"))) == self.settings.portmone_payee_id
                and item.get("status") == "PAYED"
                and item.get("payee_export_flag") == "Y"
                and item.get("chargeback") != "Y"
                and amount == expected
                and item.get("shopBillId")
            ):
                return VerifiedPayment(str(item["shopBillId"]), order_number, amount)
        return None
