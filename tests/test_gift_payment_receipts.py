"""Gift payment ledger: duplicate callbacks, mismatch and owner isolation."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.crm.models import CRMBase, GiftPaymentReceipt, GiftPurchase
from app.services.gift_payment_receipts import (
    GiftPaymentMismatch,
    VerifiedGiftPayment,
    register_verified_gift_payment,
)
from app.services.gift_purchases import create_gift_quote


@pytest.fixture
async def payment_factory(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "receipts.db"))
    async with engine.begin() as connection:
        await connection.run_sync(CRMBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _quote(factory, tmp_path, user_id=42, choice="both"):
    return await create_gift_quote(
        factory,
        settings=Settings(
            _env_file=None,
            wayforpay_wallpaper_price_uah=Decimal("15.00"),
            wayforpay_video_story_price_uah=Decimal("49.00"),
        ),
        user_id=user_id,
        choice=choice,
        goals=[f"goal {i}" for i in range(5)],
        photo_paths=[tmp_path / "portrait.jpg"],
        style="dark",
    )


@pytest.mark.asyncio
async def test_verified_callback_is_stored_once(payment_factory, tmp_path):
    purchase = await _quote(payment_factory, tmp_path)
    evidence = VerifiedGiftPayment(
        purchase_id=purchase.id,
        telegram_user_id=42,
        provider="wayforpay",
        provider_payment_id="verified-charge-123",
        amount=Decimal("64.00"),
    )
    assert await register_verified_gift_payment(payment_factory, evidence) == "new"
    assert await register_verified_gift_payment(payment_factory, evidence) == "same"
    async with payment_factory() as session:
        assert await session.scalar(select(func.count()).select_from(GiftPaymentReceipt)) == 1
        saved = await session.get(GiftPurchase, purchase.id)
        assert saved.status == "paid"


@pytest.mark.asyncio
async def test_invalid_receipts_cannot_grant_entitlement(payment_factory, tmp_path):
    purchase = await _quote(payment_factory, tmp_path)
    expected = dict(
        purchase_id=purchase.id, telegram_user_id=42, provider="wayforpay",
        provider_payment_id="charge-1", amount=Decimal("64.00"),
    )
    invalid = [
        {"telegram_user_id": 999},
        {"amount": Decimal("63.99")},
        {"currency": "USD"},
        {"provider": "unknown"},
        {"provider_payment_id": ""},
    ]
    for update in invalid:
        with pytest.raises(GiftPaymentMismatch):
            await register_verified_gift_payment(
                payment_factory, VerifiedGiftPayment(**(expected | update))
            )
    async with payment_factory() as session:
        assert await session.scalar(select(func.count()).select_from(GiftPaymentReceipt)) == 0
        saved = await session.get(GiftPurchase, purchase.id)
        assert saved.status == "quoted"


@pytest.mark.asyncio
async def test_two_charges_cannot_pay_same_quote(payment_factory, tmp_path):
    purchase = await _quote(payment_factory, tmp_path)
    evidence = VerifiedGiftPayment(
        purchase_id=purchase.id, telegram_user_id=42, provider="wayforpay",
        provider_payment_id="first", amount=Decimal("64.00"),
    )
    assert await register_verified_gift_payment(payment_factory, evidence) == "new"
    with pytest.raises(GiftPaymentMismatch, match="already paid"):
        await register_verified_gift_payment(
            payment_factory,
            VerifiedGiftPayment(
                purchase_id=purchase.id, telegram_user_id=42,
                provider="wayforpay", provider_payment_id="second",
                amount=Decimal("64.00"),
            ),
        )


@pytest.mark.asyncio
async def test_provider_charge_cannot_pay_another_quote(payment_factory, tmp_path):
    first = await _quote(payment_factory, tmp_path, user_id=42)
    second = await _quote(payment_factory, tmp_path, user_id=43)
    receipt = dict(
        telegram_user_id=42, provider="wayforpay",
        provider_payment_id="same-charge", amount=Decimal("64.00"),
    )
    assert await register_verified_gift_payment(
        payment_factory, VerifiedGiftPayment(purchase_id=first.id, **receipt)
    ) == "new"
    with pytest.raises(GiftPaymentMismatch, match="already belongs"):
        await register_verified_gift_payment(
            payment_factory, VerifiedGiftPayment(
                purchase_id=second.id, **(receipt | {"telegram_user_id": 43})
            )
        )
