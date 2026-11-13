"""Gift payment row-lock and concurrent webhook tests on isolated PostgreSQL.

Requires FOOD_PORN_TEST_DATABASE_URL to point at food_porn_test only.
Each invocation uses its own disposable random schema.
"""
from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.crm.models import GiftPaymentReceipt, GiftPurchase
from app.database.models import WayForPayPayment
from app.database.repositories import WayForPayPaymentRepository
from app.services.wayforpay import apply_verified_payment


@pytest.fixture
async def postgres_gift():
    raw = os.getenv("FOOD_PORN_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("FOOD_PORN_TEST_DATABASE_URL required")
    parsed = make_url(raw)
    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.database != "food_porn_test"
        or parsed.host not in {"127.0.0.1", "localhost"}
    ):
        pytest.fail("Only the dedicated local food_porn_test PostgreSQL database is permitted")
    url = parsed.set(drivername="postgresql+asyncpg")
    schema = "gift_test_" + uuid4().hex[:16]
    admin = create_async_engine(url, pool_pre_ping=True, connect_args={"ssl": "disable"})
    isolated = None
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        isolated = create_async_engine(url, pool_pre_ping=True, connect_args={"ssl": "disable"})

        @event.listens_for(isolated.sync_engine, "begin")
        def set_schema(connection):
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')

        async with isolated.begin() as conn:
            await conn.run_sync(GiftPurchase.__table__.create)
            await conn.run_sync(GiftPaymentReceipt.__table__.create)
            await conn.run_sync(WayForPayPayment.__table__.create)
        yield async_sessionmaker(isolated, expire_on_commit=False)
    finally:
        if isolated is not None:
            await isolated.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


async def seed_purchase(factory):
    purchase = GiftPurchase(
        request_key=uuid4().hex, telegram_user_id=456,
        product_choice="both", includes_collage=True, includes_video=True,
        currency="UAH", collage_amount=Decimal("15.00"),
        video_amount=Decimal("49.00"), total_amount=Decimal("64.00"),
        goals=["wish"] * 5, photo_paths=["/tmp/picture.jpg"],
        visual_style="dark", status="quoted",
    )
    async with factory() as session:
        session.add(purchase)
        await session.flush()
        purchase_id = purchase.id
        attempts = []
        for number in (1, 2):
            payment = WayForPayPayment(
                telegram_user_id=456, product="gift_purchase",
                reference_id=purchase_id,
                order_reference=f"fp_gift_{uuid4().hex}_{number}",
                checkout_token=f"token_{uuid4().hex}",
                amount=Decimal("64.00"), currency="UAH",
                description="Gift bundle", status="pending",
                test_mode=True, grants_entitlement=True,
            )
            session.add(payment)
            attempts.append(payment.order_reference)
        await session.commit()
    return purchase_id, attempts


@pytest.mark.asyncio
async def test_parallel_gift_callbacks_are_serialized_and_only_one_wins(postgres_gift):
    factory = postgres_gift
    purchase_id, references = await seed_purchase(factory)

    async def approve(reference):
        async with factory() as session:
            payment = await WayForPayPaymentRepository(session).by_order_reference(
                reference, lock=True
            )
            return await apply_verified_payment(
                session, payment, {
                    "transactionStatus": "Approved",
                    "authCode": "AUTH-OK", "reasonCode": "1100",
                },
            )

    results = await asyncio.wait_for(
        asyncio.gather(*(approve(ref) for ref in references)), timeout=25
    )
    assert sorted(results) == [False, True]
    winner = references[results.index(True)]
    assert await approve(winner) is True

    async with factory() as session:
        purchase = await session.get(GiftPurchase, purchase_id)
        receipt = await session.get(GiftPaymentReceipt, purchase_id)
        assert purchase.status == "paid"
        assert receipt.provider_payment_id == winner
        assert receipt.amount == Decimal("64.00")
        assert await session.scalar(
            select(func.count()).select_from(GiftPaymentReceipt)
        ) == 1
        attempts = [
            await WayForPayPaymentRepository(session).by_order_reference(ref)
            for ref in references
        ]
        assert all(attempt.status == "approved" for attempt in attempts)
        assert sum(bool(attempt.error_message) for attempt in attempts) == 1


@pytest.mark.asyncio
async def test_wrong_amount_callback_cannot_change_gift_purchase(postgres_gift):
    factory = postgres_gift
    purchase_id, references = await seed_purchase(factory)
    async with factory() as session:
        payment = await WayForPayPaymentRepository(session).by_order_reference(
            references[0], lock=True
        )
        payment.amount = Decimal("1.00")
        from app.services.wayforpay import WayForPayError
        with pytest.raises(WayForPayError, match="owner or price mismatch"):
            await apply_verified_payment(
                session, payment, {"transactionStatus": "Approved"},
            )
        await session.rollback()
    async with factory() as session:
        assert (await session.get(GiftPurchase, purchase_id)).status == "quoted"
        assert await session.get(GiftPaymentReceipt, purchase_id) is None
