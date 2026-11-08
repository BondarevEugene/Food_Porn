"""Opt-in real PostgreSQL concurrency tests for menu and wallpaper payments.

Requires FOOD_PORN_TEST_DATABASE_URL pointing to a dedicated PostgreSQL database
whose database name includes 'test'. Creates and drops only a random schema.
"""
import asyncio
import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import Customer, Menu, WallpaperOrder
from app.database.repositories import MenuRepository, WallpaperOrderRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("product", ["menu", "wallpaper"])
async def test_concurrent_payment_claims_postgres(product):
    url = os.getenv("FOOD_PORN_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FOOD_PORN_TEST_DATABASE_URL is required")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or "test" not in (parsed.database or "").lower():
        pytest.fail("Refusing to use a database without 'test' in its PostgreSQL database name")

    schema = "payment_test_" + uuid4().hex[:16]
    admin = create_async_engine(url, pool_pre_ping=True)
    isolated = None
    created = False
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        isolated = create_async_engine(
            url, pool_pre_ping=True,
            connect_args={"server_settings": {"search_path": schema}},
        )
        async with isolated.begin() as conn:
            if product == "menu":
                await conn.run_sync(lambda c: Customer.__table__.create(c, checkfirst=False))
                await conn.run_sync(lambda c: Menu.__table__.create(c, checkfirst=False))
                customer_id = (await conn.execute(text(
                    "INSERT INTO customers (telegram_user_id, name, phone, country, city, language, source_channel) "
                    "VALUES (987654321, 'Payment test', '000', 'Test', 'Test', 'UK', 'telegram') RETURNING id"
                ))).scalar_one()
                order_id = (await conn.execute(text(
                    "INSERT INTO menus (customer_id, status, is_paid, source_channel) "
                    "VALUES (:id, 'waiting_for_payment', false, 'telegram') RETURNING id"
                ), {"id": customer_id})).scalar_one()
            else:
                await conn.run_sync(lambda c: WallpaperOrder.__table__.create(c, checkfirst=False))
                order_id = (await conn.execute(text(
                    "INSERT INTO wallpaper_orders (telegram_user_id, amount, mobile_path, desktop_path, paid, source_channel) "
                    "VALUES (987654321, 10.00, 'mobile.png', 'desktop.png', false, 'telegram') RETURNING id"
                ))).scalar_one()

        factory = async_sessionmaker(isolated, expire_on_commit=False)

        async def claim(receipt):
            async with factory() as session:
                if product == "menu":
                    return await MenuRepository(session).mark_as_paid(order_id, receipt, "portmone")
                order = await session.get(WallpaperOrder, order_id)
                return await WallpaperOrderRepository(session).mark_paid(order, receipt, "portmone")

        same = await asyncio.wait_for(
            asyncio.gather(claim("receipt-1"), claim("receipt-1")), timeout=20
        )
        assert sorted(same) == [False, True]
        with pytest.raises(ValueError, match="another receipt"):
            await claim("receipt-2")
        assert await claim("receipt-1") is False

        async with factory() as session:
            if product == "menu":
                row = await session.get(Menu, order_id)
                assert row.is_paid is True
                assert row.status.value == "paid"
            else:
                row = await session.get(WallpaperOrder, order_id)
                assert row.paid is True
            assert row.payment_id == "receipt-1"
            assert row.payment_system == "portmone"
            assert row.paid_at is not None
    finally:
        if isolated is not None:
            await isolated.dispose()
        try:
            if created:
                async with admin.begin() as conn:
                    await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            await admin.dispose()
