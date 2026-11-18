"""Opt-in PostgreSQL race tests for Little Legend's append-only cost ledger.

Only a dedicated food_porn_test database is accepted; all objects live in a
random schema that is removed after the test.
"""
import asyncio
import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.little_legend import ai_cost_ledger
from app.little_legend.ai_cost_ledger import (
    CostEvidence,
    CostReceipt,
    cost_receipts,
    record_confirmed_cost,
)
from app.little_legend.writer_queue import WriterJob
from app.little_legend.writer_queue_store import writer_jobs


@pytest.mark.asyncio
async def test_cost_receipt_concurrency_and_conflicts_on_postgres(monkeypatch):
    raw_url = os.getenv("FOOD_PORN_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("FOOD_PORN_TEST_DATABASE_URL is required")
    parsed = make_url(raw_url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "food_porn_test":
        pytest.fail("Refusing to use a database other than food_porn_test")
    url = parsed.set(drivername="postgresql+asyncpg").difference_update_query(
        ["sslmode", "channel_binding"]
    )
    schema = "ll_cost_test_" + uuid4().hex[:16]
    admin = create_async_engine(url, connect_args={"ssl": "require"})
    isolated = None
    created = False
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        isolated = create_async_engine(url, connect_args={"ssl": "require"})

        @event.listens_for(isolated.sync_engine, "begin")
        def _set_schema(conn):
            conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')

        async with isolated.begin() as conn:
            await conn.run_sync(writer_jobs.create)
            await conn.run_sync(cost_receipts.create)
            job = WriterJob(
                job_id="job_ledger_concurrency_1234", story_id=42,
                owner_id=7, scene_id="opening", expected_revision=0,
                estimated_cost_usd=0.05,
            )
            await conn.execute(insert(writer_jobs).values(
                job_id=job.job_id, story_id=42, owner_id=7,
                status=job.status.value, payload=job.model_dump_json(),
                created_at=datetime(2026, 11, 18, tzinfo=UTC),
                updated_at=datetime(2026, 11, 18, tzinfo=UTC),
            ))
        factory = async_sessionmaker(isolated, expire_on_commit=False)
        monkeypatch.setattr(ai_cost_ledger, "async_session_maker", factory)

        receipt = CostReceipt(
            receipt_id="receipt_ledger_concurrency_1234",
            job_id=job.job_id, provider="test_provider",
            provider_reference="provider_charge_1234",
            amount_usd=Decimal("0.012345"),
            evidence=CostEvidence.PROVIDER_RECEIPT,
        )
        results = await asyncio.wait_for(
            asyncio.gather(*(
                record_confirmed_cost(receipt, owner_id=7, story_id=42)
                for _ in range(2)
            )),
            timeout=30,
        )
        assert sorted(results) == [False, True]
        assert await record_confirmed_cost(receipt, owner_id=7, story_id=42) is False

        conflicting = receipt.model_copy(update={"amount_usd": Decimal("0.09")})
        with pytest.raises(ValueError, match="Conflicting"):
            await record_confirmed_cost(conflicting, owner_id=7, story_id=42)

        same_id_new_reference = receipt.model_copy(update={
            "provider_reference": "different_charge_reference",
        })
        with pytest.raises(ValueError, match="Conflicting"):
            await record_confirmed_cost(same_id_new_reference, owner_id=7, story_id=42)

        with pytest.raises(PermissionError):
            await record_confirmed_cost(receipt, owner_id=8, story_id=42)

        async with factory() as session:
            rows = (await session.execute(select(cost_receipts))).mappings().all()
        assert len(rows) == 1
        assert rows[0]["amount_usd"] == Decimal("0.012345")
        assert rows[0]["owner_id"] == 7
    finally:
        if isolated is not None:
            await isolated.dispose()
        try:
            if created:
                async with admin.begin() as conn:
                    await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            await admin.dispose()
