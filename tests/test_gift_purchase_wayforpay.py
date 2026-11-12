"""Signed WayForPay gift-purchase callback and idempotent receipt regression."""
from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.crm.models import CRMBase, GiftPaymentReceipt, GiftPurchase
from app.database.models import WayForPayPayment
from app.services.gift_purchases import create_gift_quote
from app.services.wayforpay import (
    TEST_MERCHANT_ACCOUNT,
    TEST_MERCHANT_SECRET,
    WayForPayError,
    WayForPayService,
    apply_verified_payment,
    wayforpay_entitlement_is_active,
)


@pytest.fixture
async def purchase_db(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "gift_wfp.db"))
    async with engine.begin() as connection:
        await connection.run_sync(CRMBase.metadata.create_all)
        await connection.run_sync(WayForPayPayment.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        wayforpay_test_mode=True,
        public_base_url="https://example.org",
        wayforpay_merchant_domain="example.org",
        wayforpay_wallpaper_price_uah=Decimal("15.00"),
        wayforpay_video_story_price_uah=Decimal("49.00"),
    )
    purchase = await create_gift_quote(
        factory, settings=settings, user_id=42, choice="both",
        goals=[f"goal {i}" for i in range(5)],
        photo_paths=[tmp_path / "portrait.jpg"], style="dark",
    )
    yield factory, settings, purchase
    await engine.dispose()


def signed_payload(attempt: WayForPayPayment) -> dict:
    payload = {
        "merchantAccount": TEST_MERCHANT_ACCOUNT,
        "orderReference": attempt.order_reference,
        "amount": f"{attempt.amount:.2f}",
        "currency": "UAH",
        "authCode": "TEST-OK",
        "cardPan": "411111****1111",
        "transactionStatus": "Approved",
        "reasonCode": "1100",
    }
    fields = (
        "merchantAccount", "orderReference", "amount", "currency", "authCode",
        "cardPan", "transactionStatus", "reasonCode",
    )
    payload["merchantSignature"] = hmac.new(
        TEST_MERCHANT_SECRET.encode(),
        ";".join(payload[key] for key in fields).encode(),
        hashlib.md5,
    ).hexdigest()
    return payload


@pytest.mark.asyncio
async def test_signed_callback_activates_only_quoted_purchase_once(purchase_db):
    factory, settings, purchase = purchase_db
    service = WayForPayService(settings)
    async with factory() as session:
        attempt, url = await service.create_checkout(
            session, telegram_user_id=42, product="gift_purchase",
            reference_id=purchase.id, description="Gift bundle",
            amount_override=Decimal("64.00"),
        )
    assert url.endswith(attempt.checkout_token)
    payload = signed_payload(attempt)
    assert service.verify_provider_payload(attempt, payload)
    async with factory() as session:
        saved = await session.get(WayForPayPayment, attempt.id)
        assert await apply_verified_payment(session, saved, payload) is True
    async with factory() as session:
        saved = await session.get(WayForPayPayment, attempt.id)
        assert await apply_verified_payment(session, saved, payload) is True
        assert await wayforpay_entitlement_is_active(session, saved)
        quote = await session.get(GiftPurchase, purchase.id)
        receipt = await session.get(GiftPaymentReceipt, purchase.id)
        assert quote.status == "paid"
        assert receipt.provider_payment_id == attempt.order_reference
        assert receipt.amount == Decimal("64.00")
        assert receipt.provider == "wayforpay"


@pytest.mark.asyncio
async def test_wrong_price_and_owner_are_not_accepted_at_checkout(purchase_db):
    factory, settings, purchase = purchase_db
    service = WayForPayService(settings)
    for owner, price in ((55, Decimal("64")), (42, Decimal("63.99"))):
        async with factory() as session:
            with pytest.raises(WayForPayError):
                await service.create_checkout(
                    session, telegram_user_id=owner, product="gift_purchase",
                    reference_id=purchase.id, description="Gift bundle",
                    amount_override=price,
                )
    async with factory() as session:
        with pytest.raises(WayForPayError, match="requires an immutable"):
            await service.create_checkout(
                session, telegram_user_id=42, product="gift_purchase",
                reference_id=purchase.id, description="Gift bundle",
            )


@pytest.mark.asyncio
async def test_duplicate_attempt_is_not_granted_second_entitlement(purchase_db):
    factory, settings, purchase = purchase_db
    service = WayForPayService(settings)
    async with factory() as session:
        first, _ = await service.create_checkout(
            session, telegram_user_id=42, product="gift_purchase",
            reference_id=purchase.id, description="Gift bundle",
            amount_override=Decimal("64.00"),
        )
    async with factory() as session:
        second, _ = await service.create_checkout(
            session, telegram_user_id=42, product="gift_purchase",
            reference_id=purchase.id, description="Gift bundle",
            amount_override=Decimal("64.00"),
        )
    assert first.id == second.id
    async with factory() as session:
        attempt = await session.get(WayForPayPayment, first.id)
        payload = signed_payload(attempt)
        payload["amount"] = "55.00"
        assert not service.verify_provider_payload(attempt, payload)
        assert not await wayforpay_entitlement_is_active(session, attempt)
