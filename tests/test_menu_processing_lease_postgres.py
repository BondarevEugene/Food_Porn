"""Opt-in PostgreSQL integration test against a disposable TEST database only.

Set FOOD_PORN_TEST_DATABASE_URL to a dedicated database whose name contains
'test'. Never point this test at the application/production database.
"""
import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import Customer, Menu
from app.services.menu_processing_lease import MenuProcessingLease


@pytest.mark.asyncio
async def test_postgres_lease_concurrent_claim_renew_expire_and_release():
    url = os.getenv("FOOD_PORN_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set FOOD_PORN_TEST_DATABASE_URL to an isolated PostgreSQL test database")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or "test" not in (parsed.database or "").lower():
        pytest.fail("Refusing to run: test DB must be PostgreSQL and database name must contain 'test'")

    schema = "lease_test_" + uuid4().hex[:16]
    admin = create_async_engine(url, pool_pre_ping=True)
    isolated = None
    schema_created = False
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_created = True
        isolated = create_async_engine(
            url,
            pool_pre_ping=True,
            connect_args={"server_settings": {"search_path": schema}},
        )
        async with isolated.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Customer.__table__.create(sync_conn, checkfirst=False)
            )
            await conn.run_sync(
                lambda sync_conn: Menu.__table__.create(sync_conn, checkfirst=False)
            )
            customer_id = (await conn.execute(
                text(
                    "INSERT INTO customers "
                    "(telegram_user_id, name, phone, country, city, language, source_channel) "
                    "VALUES (987654321, 'Lease test', '000', 'Test', 'Test', 'UK', 'telegram') RETURNING id"
                )
            )).scalar_one()
            menu_id = (
                await conn.execute(
                    text("INSERT INTO menus (customer_id, status, is_paid, source_channel) "
                         "VALUES (:customer_id, 'queued', false, 'telegram') RETURNING id"),
                    {"customer_id": customer_id},
                )
            ).scalar_one()

        factory = async_sessionmaker(isolated, expire_on_commit=False)
        first = MenuProcessingLease(factory, menu_id)
        second = MenuProcessingLease(factory, menu_id)
        claims = await asyncio.wait_for(
            asyncio.gather(first.acquire(), second.acquire()), timeout=15
        )
        assert sorted(claims) == [False, True]
        owner, loser = (first, second) if claims[0] else (second, first)
        assert await owner.renew() is True
        assert await loser.release() is None
        assert await loser.acquire() is False

        # Simulate expiry without waiting five minutes.
        async with factory() as session:
            await session.execute(
                text("UPDATE menus SET processing_lease_until = now() - interval '1 second' "
                     "WHERE id = :id"),
                {"id": menu_id},
            )
            await session.commit()
        assert await loser.acquire() is True
        assert await owner.renew() is False
        await owner.release()
        assert await loser.renew() is True
        await loser.release()
        assert await first.acquire() is True
        await first.release()
    finally:
        if isolated is not None:
            await isolated.dispose()
        try:
            if schema_created:
                async with admin.begin() as conn:
                    await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            await admin.dispose()
