"""Конкурентні оплати WayForPay в ізольованій PostgreSQL тестовій схемі."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import Customer, Menu, WallpaperOrder, WayForPayPayment
from app.database.repositories import WayForPayPaymentRepository
from app.services.wayforpay import apply_verified_payment


@pytest.mark.asyncio
@pytest.mark.parametrize("product", ["menu", "wallpaper"])
async def test_concurrent_wayforpay_approvals_preserve_single_entitlement(product):
    """Дві одночасні підтверджені транзакції не перезаписують одна одну."""
    raw_url = os.getenv("FOOD_PORN_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("FOOD_PORN_TEST_DATABASE_URL is required")
    parsed = make_url(raw_url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "food_porn_test":
        pytest.fail("Refusing to run outside the dedicated food_porn_test database")

    url = parsed.set(drivername="postgresql+asyncpg").difference_update_query(
        ["sslmode", "channel_binding"]
    )
    schema = "wfp_test_" + uuid4().hex[:16]
    admin = create_async_engine(url, pool_pre_ping=True, connect_args={"ssl": "require"})
    isolated = None
    created = False
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        isolated = create_async_engine(
            url, pool_pre_ping=True, connect_args={"ssl": "require"}
        )

        @event.listens_for(isolated.sync_engine, "begin")
        def _set_test_schema(conn):
            conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')

        async with isolated.begin() as conn:
            if product == "menu":
                await conn.run_sync(lambda c: Customer.__table__.create(c))
                await conn.run_sync(lambda c: Menu.__table__.create(c))
                customer_id = (
                    await conn.execute(
                        text(
                            "INSERT INTO customers "
                            "(telegram_user_id, name, phone, country, city, language, source_channel) "
                            "VALUES (987654321, 'WFP test', '000', 'Test', 'Test', 'UK', 'telegram') "
                            "RETURNING id"
                        )
                    )
                ).scalar_one()
                order_id = (
                    await conn.execute(
                        text(
                            "INSERT INTO menus (customer_id, status, is_paid, source_channel) "
                            "VALUES (:customer_id, 'waiting_for_payment', false, 'telegram') RETURNING id"
                        ),
                        {"customer_id": customer_id},
                    )
                ).scalar_one()
            else:
                await conn.run_sync(lambda c: WallpaperOrder.__table__.create(c))
                order_id = (
                    await conn.execute(
                        text(
                            "INSERT INTO wallpaper_orders "
                            "(telegram_user_id, amount, mobile_path, desktop_path, paid, "
                            "source_channel, locked_scene_indexes, visual_style) "
                            "VALUES (987654321, 10.00, 'mobile.png', 'desktop.png', "
                            "false, 'telegram', '[]', 'dark') RETURNING id"
                        )
                    )
                ).scalar_one()

            await conn.run_sync(lambda c: WayForPayPayment.__table__.create(c))
            references = [
                f"fp_{product}_{order_id}_concurrent_{index}" for index in range(2)
            ]
            for index, reference in enumerate(references):
                await conn.execute(
                    text(
                        "INSERT INTO wayforpay_payments "
                        "(telegram_user_id, product, reference_id, order_reference, "
                        "checkout_token, amount, currency, description, status, "
                        "test_mode, grants_entitlement) "
                        "VALUES (987654321, :product, :order_id, :reference, "
                        ":token, 5.00, 'UAH', 'Test checkout', 'pending', true, true)"
                    ),
                    {
                        "product": product,
                        "order_id": str(order_id),
                        "reference": reference,
                        "token": f"token-{uuid4().hex}-{index}",
                    },
                )

        factory = async_sessionmaker(isolated, expire_on_commit=False)

        async def approve(reference):
            async with factory() as session:
                attempt = await WayForPayPaymentRepository(session).by_order_reference(
                    reference, lock=True
                )
                return await apply_verified_payment(
                    session,
                    attempt,
                    {
                        "transactionStatus": "Approved",
                        "authCode": f"AUTH-{reference}",
                        "reasonCode": "1100",
                    },
                )

        results = await asyncio.wait_for(
            asyncio.gather(*(approve(reference) for reference in references)),
            timeout=30,
        )
        assert sorted(results) == [False, True]

        async with factory() as session:
            model = Menu if product == "menu" else WallpaperOrder
            order = await session.get(model, order_id)
            assert (order.is_paid if product == "menu" else order.paid) is True
            assert order.payment_system == "wayforpay"
            assert order.payment_id in references
            attempts = [
                await WayForPayPaymentRepository(session).by_order_reference(reference)
                for reference in references
            ]
            assert all(attempt.status == "approved" for attempt in attempts)
            assert sum(
                attempt.error_message is not None
                and "duplicate_payment" in attempt.error_message
                for attempt in attempts
            ) == 1
            assert sum(
                attempt.error_message is None for attempt in attempts
            ) == 1

        # Повторне підтвердження першої транзакції не змінює право доступу.
        winner = references[results.index(True)]
        assert await approve(winner) is True
        async with factory() as session:
            order = await session.get(Menu if product == "menu" else WallpaperOrder, order_id)
            assert order.payment_id == winner
    finally:
        if isolated is not None:
            await isolated.dispose()
        try:
            if created:
                async with admin.begin() as conn:
                    await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            await admin.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("product", ["menu", "wallpaper"])
async def test_concurrent_webhook_and_telegram_check_same_payment(product):
    """Webhook та Telegram-перевірка одночасно підтверджують одну спробу."""
    raw_url = os.getenv("FOOD_PORN_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("FOOD_PORN_TEST_DATABASE_URL is required")
    parsed = make_url(raw_url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "food_porn_test":
        pytest.fail("Refusing to run outside the dedicated food_porn_test database")

    url = parsed.set(drivername="postgresql+asyncpg").difference_update_query(
        ["sslmode", "channel_binding"]
    )
    schema = "wfp_race_" + uuid4().hex[:16]
    admin = create_async_engine(url, pool_pre_ping=True, connect_args={"ssl": "require"})
    isolated = None
    created = False
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        isolated = create_async_engine(
            url, pool_pre_ping=True, connect_args={"ssl": "require"}
        )

        @event.listens_for(isolated.sync_engine, "begin")
        def _set_test_schema(conn):
            conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')

        async with isolated.begin() as conn:
            if product == "menu":
                await conn.run_sync(lambda c: Customer.__table__.create(c))
                await conn.run_sync(lambda c: Menu.__table__.create(c))
                customer_id = (
                    await conn.execute(
                        text(
                            "INSERT INTO customers "
                            "(telegram_user_id, name, phone, country, city, language, source_channel) "
                            "VALUES (987654321, 'Race test', '000', 'Test', 'Test', 'UK', 'telegram') "
                            "RETURNING id"
                        )
                    )
                ).scalar_one()
                order_id = (
                    await conn.execute(
                        text(
                            "INSERT INTO menus (customer_id, status, is_paid, source_channel) "
                            "VALUES (:id, 'waiting_for_payment', false, 'telegram') RETURNING id"
                        ),
                        {"id": customer_id},
                    )
                ).scalar_one()
            else:
                await conn.run_sync(lambda c: WallpaperOrder.__table__.create(c))
                order_id = (
                    await conn.execute(
                        text(
                            "INSERT INTO wallpaper_orders "
                            "(telegram_user_id, amount, mobile_path, desktop_path, paid, "
                            "source_channel, locked_scene_indexes, visual_style) "
                            "VALUES (987654321, 10.00, 'mobile.png', 'desktop.png', "
                            "false, 'telegram', '[]', 'dark') RETURNING id"
                        )
                    )
                ).scalar_one()
            await conn.run_sync(lambda c: WayForPayPayment.__table__.create(c))
            reference = f"fp_{product}_{order_id}_same_attempt"
            await conn.execute(
                text(
                    "INSERT INTO wayforpay_payments "
                    "(telegram_user_id, product, reference_id, order_reference, "
                    "checkout_token, amount, currency, description, status, "
                    "test_mode, grants_entitlement) "
                    "VALUES (987654321, :product, :order_id, :reference, "
                    ":token, 5.00, 'UAH', 'Test checkout', 'pending', true, true)"
                ),
                {
                    "product": product,
                    "order_id": str(order_id),
                    "reference": reference,
                    "token": f"token-{uuid4().hex}",
                },
            )

        factory = async_sessionmaker(isolated, expire_on_commit=False)

        async def confirm(lock):
            async with factory() as session:
                repository = WayForPayPaymentRepository(session)
                if lock:
                    attempt = await repository.by_order_reference(reference, lock=True)
                else:
                    attempt = await repository.by_order_reference(reference)
                return await apply_verified_payment(
                    session,
                    attempt,
                    {
                        "transactionStatus": "Approved",
                        "authCode": "AUTH-SAME",
                        "reasonCode": "1100",
                    },
                )

        results = await asyncio.wait_for(
            asyncio.gather(confirm(True), confirm(False)), timeout=30
        )
        assert results == [True, True]

        async with factory() as session:
            order = await session.get(Menu if product == "menu" else WallpaperOrder, order_id)
            assert (order.is_paid if product == "menu" else order.paid) is True
            assert order.payment_id == reference
            assert order.payment_system == "wayforpay"
            attempt = await WayForPayPaymentRepository(session).by_order_reference(reference)
            assert attempt.status == "approved"
            assert attempt.error_message is None
            assert attempt.paid_at is not None
    finally:
        if isolated is not None:
            await isolated.dispose()
        try:
            if created:
                async with admin.begin() as conn:
                    await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            await admin.dispose()
