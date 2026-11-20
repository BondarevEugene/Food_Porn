"""Durable, idempotent Little Legend fulfillment requests.

This queue records paid-book work. A separate worker must enforce consent,
quality gates and production budgets before generating any paid assets.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.little_legend.payment_entitlement import has_verified_entitlement

metadata = MetaData()
fulfillment_jobs = Table(
    "little_legend_fulfillment_jobs",
    metadata,
    Column("quote_id", BigInteger, ForeignKey("little_legend_order_quotes.id"), primary_key=True),
    Column("owner_id", BigInteger, nullable=False),
    Column("status", String(24), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("asset_key", String(128), nullable=True),
    Column("delivery_started_at", DateTime(timezone=True), nullable=True),
    Column("delivered_at", DateTime(timezone=True), nullable=True),
    Column("lease_token", String(36), nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("lease_attempts", Integer, nullable=False, server_default="0"),
)


async def request_paid_fulfillment(
    session: AsyncSession, *, quote_id: int, owner_id: int
) -> str:
    """Create exactly one durable request after verified payment.

    Does not call AI or generate files. Safe for concurrent webhook retries.
    """
    if not await has_verified_entitlement(
        session, quote_id=quote_id, owner_id=owner_id
    ):
        raise PermissionError("Verified payment required")
    now = datetime.now(UTC)
    await session.execute(
        pg_insert(fulfillment_jobs)
        .values(
            quote_id=quote_id,
            owner_id=owner_id,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=[fulfillment_jobs.c.quote_id])
    )
    status = await session.scalar(
        select(fulfillment_jobs.c.status).where(
            fulfillment_jobs.c.quote_id == quote_id,
            fulfillment_jobs.c.owner_id == owner_id,
        )
    )
    if status is None:
        raise PermissionError("Fulfillment owner mismatch")
    return status
