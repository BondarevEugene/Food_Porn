"""Persist externally VERIFIED gift payment evidence exactly once.

Call this only after the payment-provider adapter has checked its signature,
payment status and provider order reference. No HTTP route accepts these
values directly from a buyer.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.crm.models import GiftPaymentReceipt, GiftPurchase


@dataclass(frozen=True, slots=True)
class VerifiedGiftPayment:
    """Internal adapter output; not an API input schema."""

    purchase_id: str
    telegram_user_id: int
    provider: str
    provider_payment_id: str
    amount: Decimal
    currency: str = "UAH"


class GiftPaymentMismatch(ValueError):
    """A receipt does not match the immutable order quote."""


async def register_verified_gift_payment(
    factory: async_sessionmaker[AsyncSession], evidence: VerifiedGiftPayment
) -> str:
    """Return 'new' or 'same', reject conflicting or duplicate charges.

    This stores the confirmation, not a delivery entitlement. Production
    checkout must stay disabled until fulfillment is implemented.
    """
    if evidence.provider not in {"wayforpay", "portmone", "telegram_stars"}:
        raise GiftPaymentMismatch("Unsupported payment provider")
    if not evidence.provider_payment_id or len(evidence.provider_payment_id) > 180:
        raise GiftPaymentMismatch("Invalid provider reference")
    if (
        not evidence.amount.is_finite()
        or evidence.amount <= 0
        or evidence.amount.as_tuple().exponent < -2
    ):
        raise GiftPaymentMismatch("Invalid paid amount")
    async with factory() as session:
        purchase = await session.scalar(
            select(GiftPurchase).where(
                GiftPurchase.id == evidence.purchase_id
            ).with_for_update()
        )
        if purchase is None or purchase.telegram_user_id != evidence.telegram_user_id:
            raise GiftPaymentMismatch("Purchase does not belong to payer")
        if purchase.currency != evidence.currency or purchase.total_amount != evidence.amount:
            raise GiftPaymentMismatch("Receipt amount or currency mismatch")
        existing = await session.get(GiftPaymentReceipt, purchase.id)
        if existing is not None:
            if (
                existing.provider == evidence.provider
                and existing.provider_payment_id == evidence.provider_payment_id
                and existing.amount == evidence.amount
                and existing.currency == evidence.currency
            ):
                return "same"
            raise GiftPaymentMismatch("Purchase was already paid with another charge")
        if purchase.status != "quoted":
            raise GiftPaymentMismatch("Purchase is no longer awaiting verification")
        collision = await session.scalar(
            select(GiftPaymentReceipt.purchase_id).where(
                GiftPaymentReceipt.provider_payment_id == evidence.provider_payment_id
            )
        )
        if collision is not None:
            raise GiftPaymentMismatch("Provider receipt already belongs to another purchase")
        session.add(GiftPaymentReceipt(
            purchase_id=purchase.id,
            provider=evidence.provider,
            provider_payment_id=evidence.provider_payment_id,
            amount=evidence.amount,
            currency=evidence.currency,
        ))
        purchase.status = "paid"
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise GiftPaymentMismatch("Concurrent or duplicate payment record") from exc
        return "new"
