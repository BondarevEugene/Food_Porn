"""Durable file registry: explicit ownership and fail-closed retention.

This table is metadata only. Cloud uploads are NOT registered implicitly, and
absence from this table never grants permission to delete an object.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

metadata = MetaData()

artifacts = Table(
    "crm_storage_artifacts",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("bot_id", String(40), nullable=False),
    Column("connection", String(60), nullable=False),
    Column("bucket", String(255), nullable=False),
    Column("object_key", String(1024), nullable=False),
    Column("order_type", String(40), nullable=False),
    Column("order_id", String(100), nullable=False),
    Column("kind", String(50), nullable=False),
    Column("bytes", BigInteger, nullable=False),
    Column("etag", String(255), nullable=True),
    Column("state", String(24), nullable=False, server_default="protected"),
    Column("retention_hold", Boolean, nullable=False, server_default="true"),
    Column("registered_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "connection", "bucket", "object_key",
        name="uq_crm_storage_artifact_object",
    ),
    CheckConstraint("bytes >= 0", name="ck_crm_storage_artifact_size"),
    CheckConstraint(
        "state IN ('protected', 'orphan_candidate', 'quarantined', 'deleted')",
        name="ck_crm_storage_artifact_state",
    ),
    Index("ix_crm_storage_artifact_order", "bot_id", "order_type", "order_id"),
)


async def register(
    session: AsyncSession,
    *,
    bot_id: str,
    connection: str,
    bucket: str,
    object_key: str,
    order_type: str,
    order_id: str,
    kind: str,
    bytes_count: int,
    etag: str | None = None,
) -> int:
    """Register a verified object; never silently reassign an existing key."""
    if not all((bot_id, connection, bucket, object_key, order_type, order_id, kind)):
        raise ValueError("Storage artifact identity is incomplete")
    if bytes_count < 0:
        raise ValueError("Storage artifact size cannot be negative")
    existing = (await session.execute(
        select(artifacts).where(
            artifacts.c.connection == connection,
            artifacts.c.bucket == bucket,
            artifacts.c.object_key == object_key,
        ).with_for_update()
    )).mappings().one_or_none()
    if existing:
        expected = (
            bot_id, order_type, order_id, kind, bytes_count, etag,
        )
        actual = (
            existing["bot_id"], existing["order_type"], existing["order_id"],
            existing["kind"], existing["bytes"], existing["etag"],
        )
        if actual != expected or existing["state"] == "deleted":
            raise PermissionError("Existing artifact cannot be reassigned or replaced")
        return existing["id"]
    now = datetime.now(UTC)
    result = await session.execute(artifacts.insert().values(
        bot_id=bot_id, connection=connection, bucket=bucket,
        object_key=object_key, order_type=order_type, order_id=order_id,
        kind=kind, bytes=bytes_count, etag=etag,
        state="protected", retention_hold=True,
        registered_at=now, updated_at=now,
    ).returning(artifacts.c.id))
    return result.scalar_one()


async def order_artifacts(
    session: AsyncSession, *, bot_id: str, order_type: str, order_id: str,
) -> list[dict]:
    rows = (await session.execute(select(artifacts).where(
        artifacts.c.bot_id == bot_id,
        artifacts.c.order_type == order_type,
        artifacts.c.order_id == order_id,
    ).order_by(artifacts.c.registered_at.desc()))).mappings().all()
    return [dict(row) for row in rows]
