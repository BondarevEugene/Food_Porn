"""
==========================================================
FOOD_PORN

Module: WayForPay Hosted Checkout
Layer: Application Service

Responsibilities:
    - Build signed hosted-payment requests without touching card data
    - Verify callbacks and CHECK_STATUS responses with HMAC-MD5
    - Create isolated, idempotent checkout attempts for both products
==========================================================
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Menu, MenuStatus, WallpaperOrder, WayForPayPayment
from app.database.repositories import WayForPayPaymentRepository

WAYFORPAY_CHECKOUT_URL = "https://secure.wayforpay.com/pay"
WAYFORPAY_API_URL = "https://api.wayforpay.com/api"

# Public sandbox merchant published in the official WayForPay documentation.
# It is deliberately not a production credential.
TEST_MERCHANT_ACCOUNT = "test_merch_n1"
TEST_MERCHANT_SECRET = "flk3409refn54t54t*FNJRET"
PRODUCTS = frozenset({"menu", "wallpaper"})


class WayForPayError(RuntimeError):
    """The checkout request or provider response failed closed."""


@dataclass(frozen=True)
class WayForPayCredentials:
    account: str
    secret: str
    domain: str
    public_base_url: str


def _money(value: Decimal | str | float) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise WayForPayError("Invalid WayForPay amount") from exc
    if amount <= 0:
        raise WayForPayError("WayForPay amount must be positive")
    return amount


def _amount_text(value: Decimal | str | float) -> str:
    return f"{_money(value):.2f}"


def _signature(secret: str, values: list[Any]) -> str:
    source = ";".join(str(value) for value in values)
    return hmac.new(secret.encode("utf-8"), source.encode("utf-8"), hashlib.md5).hexdigest()


class WayForPayService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def credentials(self) -> WayForPayCredentials:
        account = self.settings.wayforpay_merchant_account.strip()
        secret = self.settings.wayforpay_merchant_secret_key.get_secret_value().strip()
        if self.settings.wayforpay_test_mode:
            account = account or TEST_MERCHANT_ACCOUNT
            secret = secret or TEST_MERCHANT_SECRET

        base = self.settings.public_base_url.strip().rstrip("/")
        if not base and self.settings.miniapp_url:
            parsed_miniapp = urlparse(self.settings.miniapp_url.strip())
            if parsed_miniapp.scheme and parsed_miniapp.netloc:
                base = f"{parsed_miniapp.scheme}://{parsed_miniapp.netloc}"
        if not base:
            railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
            if railway_domain:
                base = f"https://{railway_domain}"

        parsed = urlparse(base)
        domain = self.settings.wayforpay_merchant_domain.strip()
        domain = urlparse(domain).netloc if "://" in domain else domain
        domain = domain.strip().strip("/") or (parsed.hostname or "")
        if not account or not secret:
            raise WayForPayError("WayForPay merchant credentials are not configured")
        if parsed.scheme != "https" or not parsed.hostname:
            raise WayForPayError("PUBLIC_BASE_URL must be a public HTTPS address")
        if not domain:
            raise WayForPayError("WAYFORPAY_MERCHANT_DOMAIN is not configured")
        return WayForPayCredentials(account, secret, domain, base)

    @property
    def ready(self) -> bool:
        try:
            self.credentials()
        except WayForPayError:
            return False
        return True

    def price_for(self, product: str) -> Decimal:
        if product == "menu":
            return _money(self.settings.wayforpay_menu_price_uah)
        if product == "wallpaper":
            return _money(self.settings.wayforpay_wallpaper_price_uah)
        raise WayForPayError("Unsupported WayForPay product")

    def checkout_url(self, payment: WayForPayPayment) -> str:
        credentials = self.credentials()
        return f"{credentials.public_base_url}/payments/wayforpay/checkout/{payment.checkout_token}"

    async def create_checkout(
        self,
        session: AsyncSession,
        *,
        telegram_user_id: int,
        product: str,
        reference_id: str | int,
        description: str,
        grants_entitlement: bool = True,
    ) -> tuple[WayForPayPayment, str]:
        if product not in PRODUCTS:
            raise WayForPayError("Unsupported WayForPay product")
        self.credentials()
        amount = self.price_for(product)
        repository = WayForPayPaymentRepository(session)
        existing = await repository.latest_for_product(
            product, str(reference_id), telegram_user_id
        )
        if (
            existing is not None
            and existing.status in {"pending", "approved"}
            and existing.amount == amount
            and existing.test_mode == self.settings.wayforpay_test_mode
            and existing.grants_entitlement == grants_entitlement
        ):
            return existing, self.checkout_url(existing)

        suffix = secrets.token_hex(5)
        payment = await repository.create(
            telegram_user_id=telegram_user_id,
            product=product,
            reference_id=str(reference_id),
            order_reference=f"fp_{product}_{reference_id}_{suffix}",
            checkout_token=secrets.token_urlsafe(32),
            amount=amount,
            description=description,
            test_mode=self.settings.wayforpay_test_mode,
            grants_entitlement=grants_entitlement,
        )
        return payment, self.checkout_url(payment)

    def form_fields(self, payment: WayForPayPayment) -> dict[str, str | list[str]]:
        credentials = self.credentials()
        order_date = int(payment.created_at.timestamp()) if payment.created_at else int(time.time())
        product_name = [payment.description]
        product_count = ["1"]
        product_price = [_amount_text(payment.amount)]
        signature_values: list[Any] = [
            credentials.account,
            credentials.domain,
            payment.order_reference,
            order_date,
            _amount_text(payment.amount),
            payment.currency,
            *product_name,
            *product_count,
            *product_price,
        ]
        return {
            "merchantAccount": credentials.account,
            "merchantAuthType": "SimpleSignature",
            "merchantDomainName": credentials.domain,
            "merchantSignature": _signature(credentials.secret, signature_values),
            "orderReference": payment.order_reference,
            "orderDate": str(order_date),
            "amount": _amount_text(payment.amount),
            "currency": payment.currency,
            "productName[]": product_name,
            "productPrice[]": product_price,
            "productCount[]": product_count,
            "returnUrl": f"{credentials.public_base_url}/payments/wayforpay/return",
            "serviceUrl": f"{credentials.public_base_url}/payments/wayforpay/webhook",
        }

    def verify_provider_payload(
        self, payment: WayForPayPayment, payload: dict[str, Any]
    ) -> bool:
        credentials = self.credentials()
        try:
            amount = _money(payload["amount"])
        except (KeyError, WayForPayError):
            return False
        if (
            str(payload.get("merchantAccount", "")) != credentials.account
            or str(payload.get("orderReference", "")) != payment.order_reference
            or str(payload.get("currency", "")) != payment.currency
            or amount != payment.amount
        ):
            return False
        values = [
            payload.get("merchantAccount", ""),
            payload.get("orderReference", ""),
            payload.get("amount", ""),
            payload.get("currency", ""),
            payload.get("authCode", ""),
            payload.get("cardPan", ""),
            payload.get("transactionStatus", ""),
            payload.get("reasonCode", ""),
        ]
        expected = _signature(credentials.secret, values)
        return hmac.compare_digest(expected, str(payload.get("merchantSignature", "")))

    def callback_ack(self, order_reference: str) -> dict[str, str | int]:
        credentials = self.credentials()
        timestamp = int(time.time())
        status = "accept"
        return {
            "orderReference": order_reference,
            "status": status,
            "time": timestamp,
            "signature": _signature(
                credentials.secret, [order_reference, status, timestamp]
            ),
        }

    async def check_status(self, payment: WayForPayPayment) -> dict[str, Any]:
        credentials = self.credentials()
        payload = {
            "transactionType": "CHECK_STATUS",
            "merchantAccount": credentials.account,
            "orderReference": payment.order_reference,
            "merchantSignature": _signature(
                credentials.secret, [credentials.account, payment.order_reference]
            ),
            "apiVersion": 1,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(WAYFORPAY_API_URL, json=payload)
            response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not self.verify_provider_payload(payment, data):
            raise WayForPayError("WayForPay returned an invalid signed status")
        return data


def safe_provider_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep diagnostics without persisting even masked cardholder data."""
    allowed = {
        "merchantAccount",
        "orderReference",
        "amount",
        "currency",
        "authCode",
        "transactionStatus",
        "reasonCode",
        "reason",
        "processingDate",
        "fee",
    }
    return {key: payload[key] for key in allowed if key in payload}

async def wayforpay_entitlement_is_active(
    session: AsyncSession,
    payment: WayForPayPayment,
) -> bool:
    """Return True only when this exact WayForPay attempt owns the order."""
    if payment.status != "approved":
        return False

    if not payment.grants_entitlement:
        return True

    try:
        reference_id = int(payment.reference_id)
    except (TypeError, ValueError):
        return False

    if payment.product == "menu":
        menu = await session.get(Menu, reference_id)
        if menu is None:
            return False

        await session.refresh(menu, ["customer"])

        return (
            menu.customer.telegram_user_id == payment.telegram_user_id
            and menu.is_paid
            and menu.payment_system == "wayforpay"
            and menu.payment_id == payment.order_reference
        )

    if payment.product == "wallpaper":
        order = await session.get(WallpaperOrder, reference_id)
        if order is None:
            return False

        return (
            order.telegram_user_id == payment.telegram_user_id
            and order.paid
            and order.payment_system == "wayforpay"
            and order.payment_id == payment.order_reference
        )

    return False

async def apply_verified_payment(
    session: AsyncSession,
    payment: WayForPayPayment,
    payload: dict[str, Any],
) -> bool:
    """
    Persist a verified provider response.

    True means this exact WayForPay attempt owns the entitlement.
    False means the provider did not approve the payment or the order
    was already paid by another payment attempt/provider.
    """
    if payment.product not in PRODUCTS:
        raise WayForPayError("Unsupported WayForPay product")

    transaction_status = str(payload.get("transactionStatus", ""))
    payment.transaction_status = transaction_status[:40]
    payment.reason_code = str(payload.get("reasonCode", ""))[:40] or None
    payment.provider_payload = safe_provider_payload(payload)

    if transaction_status != "Approved":
        if payment.status != "approved":
            payment.status = "failed"
            payment.error_message = str(
                payload.get("reason", transaction_status)
            )[:1000]

        await session.commit()
        return False

    if not payment.grants_entitlement:
        payment.status = "approved"
        payment.provider_payment_id = str(
            payload.get("authCode") or payment.order_reference
        )[:120]
        payment.error_message = None
        payment.paid_at = payment.paid_at or datetime.now(UTC)

        await session.commit()
        return True

    try:
        reference_id = int(payment.reference_id)
    except (TypeError, ValueError) as exc:
        raise WayForPayError("Invalid payment reference") from exc

    # Lock the actual product row before deciding who owns its entitlement.
    if payment.product == "menu":
        product = await session.get(
            Menu, reference_id, with_for_update=True
        )
        if product is None:
            raise WayForPayError("Menu no longer exists")

        await session.refresh(product, ["customer"])

        if product.customer.telegram_user_id != payment.telegram_user_id:
            raise WayForPayError("Payment owner mismatch")

        already_paid = product.is_paid
        existing_provider = product.payment_system
        existing_payment_id = product.payment_id

    elif payment.product == "wallpaper":
        product = await session.get(
            WallpaperOrder, reference_id, with_for_update=True
        )
        if product is None:
            raise WayForPayError("Gift order no longer exists")

        if product.telegram_user_id != payment.telegram_user_id:
            raise WayForPayError("Gift order owner mismatch")

        already_paid = product.paid
        existing_provider = product.payment_system
        existing_payment_id = product.payment_id

    else:
        # Defensive guard. Never route unknown products to wallpaper.
        raise WayForPayError("Unsupported WayForPay product")

    # Record the real provider result even when another payment already
    # Record the real provider result, even if another payment owns the order.
    payment.status = "approved"
    payment.provider_payment_id = str(
        payload.get("authCode") or payment.order_reference
    )[:120]
    payment.paid_at = payment.paid_at or datetime.now(UTC)

    if already_paid:
        same_attempt = (
            existing_provider == "wayforpay"
            and existing_payment_id == payment.order_reference
        )

        if same_attempt:
            payment.error_message = None
        else:
            payment.error_message = (
                "duplicate_payment: provider approved this transaction, "
                f"but order is already paid via "
                f"{existing_provider or 'unknown'}; "
                "manual reconciliation/refund may be required"
            )

        await session.commit()
        return same_attempt

    payment.error_message = None

    # The product is not paid yet. This WayForPay attempt grants it.
    if payment.product == "menu":
        product.is_paid = True
        product.payment_id = payment.order_reference
        product.payment_system = "wayforpay"
        product.price_amount = payment.amount
        product.paid_at = datetime.now(UTC)
        product.status = MenuStatus.PAID
    else:
        product.paid = True
        product.payment_id = payment.order_reference
        product.payment_system = "wayforpay"
        product.amount = payment.amount
        product.paid_at = datetime.now(UTC)

    await session.commit()
    return True
