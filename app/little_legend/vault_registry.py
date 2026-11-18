"""Durable private-media metadata registry, without media upload or deletion.

No object storage is connected. Registry rows are intentionally internal only.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    and_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.little_legend.secure_vault import AssetState, VaultAsset, authorize_asset

metadata = MetaData()
vault_assets = Table(
    "little_legend_vault_assets",
    metadata,
    Column("asset_id", String(48), primary_key=True),
    Column("owner_id", BigInteger, nullable=False),
    Column(
        "story_id", Integer,
        nullable=False,
    ),
    Column("object_key", String(120), nullable=False, unique=True),
    Column("state", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True)),
    Column("deletion_attempts", Integer, nullable=False, default=0),
    Column("last_error_code", String(64)),
    CheckConstraint("deletion_attempts >= 0", name="ck_ll_vault_attempts"),
    Index("ix_ll_vault_owner_story", "owner_id", "story_id"),
    Index("ix_ll_vault_expiry", "state", "expires_at"),
)


async def register_asset(
    session: AsyncSession, asset: VaultAsset, *, owner_id: int, story_id: int
) -> None:
    """Only metadata may be registered; callers must verify story ownership."""
    authorize_asset(asset, owner_id=owner_id, story_id=story_id)
    if asset.state != AssetState.RESERVED:
        raise ValueError("New assets must be reserved")
    # Owner check is part of INSERT, not merely a caller-side assertion.
    from sqlalchemy import insert

    await session.execute(
        insert(vault_assets).from_select(
            [
                "asset_id", "owner_id", "story_id", "object_key", "state",
                "created_at", "expires_at", "deleted_at", "deletion_attempts",
                "last_error_code",
            ],
            select(
                asset.asset_id, asset.owner_id, asset.story_id, asset.object_key,
                asset.state.value, asset.created_at, asset.expires_at,
                asset.deleted_at, asset.deletion_attempts, asset.last_error_code,
            ).where(
                select(1)
                .select_from(stories_table)
                .where(
                    stories_table.c.id == story_id,
                    stories_table.c.owner_id == owner_id,
                )
                .exists()
            ),
        )
    )


# Table stub for SQL expressions; real DDL is defined in router's metadata.
stories_table = Table(
    "little_legend_stories", metadata,
    Column("id", Integer, primary_key=True),
    Column("owner_id", BigInteger, nullable=False),
    extend_existing=True,
)


async def request_expired_deletions(
    session: AsyncSession, *, now: datetime | None = None, batch_size: int = 100
) -> list[str]:
    """Queue expired metadata for a future object-store deletion worker.

    Does NOT delete objects. The worker must confirm physical deletion before
    advancing to DELETED; do not report this as successful erasure.
    """
    if not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be 1..500")
    instant = now or datetime.now(UTC)
    rows = (
        await session.execute(
            select(vault_assets.c.asset_id)
            .where(
                and_(
                    vault_assets.c.expires_at <= instant,
                    vault_assets.c.state.in_(
                        [
                            AssetState.RESERVED.value,
                            AssetState.STORED.value,
                            AssetState.DELETE_FAILED.value,
                        ]
                    ),
                )
            )
            .order_by(vault_assets.c.expires_at, vault_assets.c.asset_id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()
    if rows:
        await session.execute(
            update(vault_assets)
            .where(vault_assets.c.asset_id.in_(rows))
            .values(state=AssetState.DELETION_PENDING.value)
        )
    return list(rows)


async def vault_summary(
    session: AsyncSession, *, owner_id: int, story_id: int
) -> dict[str, int]:
    """Metadata counts only, scoped by both owner and story."""
    from sqlalchemy import func

    rows = (
        await session.execute(
            select(vault_assets.c.state, func.count())
            .where(
                vault_assets.c.owner_id == owner_id,
                vault_assets.c.story_id == story_id,
            )
            .group_by(vault_assets.c.state)
        )
    ).all()
    return {state: count for state, count in rows}
