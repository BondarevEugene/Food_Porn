"""Neon-backed metadata repository for private child-photo assets.

Stores only ownership, lifecycle and opaque R2 keys; never photograph bytes.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    select,
    update,
)

from app.database.session import async_session_maker
from app.little_legend.secure_vault import AssetState, VaultAsset

photo_metadata = MetaData()
photo_assets = Table(
    "little_legend_photo_assets", photo_metadata,
    Column("asset_id", String(48), primary_key=True),
    Column("owner_id", BigInteger, nullable=False),
    Column("story_id", Integer, nullable=False),
    Column("object_key", String(96), nullable=False, unique=True),
    Column("state", String(24), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True)),
    Column("deletion_attempts", Integer, nullable=False, default=0),
    Column("last_error_code", String(64)),
)


class NeonVaultMetadataRepository:
    async def get_asset(self, *, asset_id: str) -> VaultAsset | None:
        async with async_session_maker() as session:
            row = (await session.execute(
                select(photo_assets).where(photo_assets.c.asset_id == asset_id)
            )).mappings().one_or_none()
        return VaultAsset.model_validate(dict(row)) if row else None

    async def create_asset(self, *, asset: VaultAsset) -> None:
        if asset.state != AssetState.RESERVED:
            raise ValueError("Only reserved photo assets may be created")
        async with async_session_maker() as session:
            await session.execute(insert(photo_assets).values(
                asset_id=asset.asset_id,
                owner_id=asset.owner_id,
                story_id=asset.story_id,
                object_key=asset.object_key,
                state=asset.state.value,
                created_at=asset.created_at,
                expires_at=asset.expires_at,
                deleted_at=asset.deleted_at,
                deletion_attempts=asset.deletion_attempts,
                last_error_code=asset.last_error_code,
            ))
            await session.commit()

    async def mark_stored(self, *, asset_id: str) -> None:
        async with async_session_maker() as session:
            result = await session.execute(
                update(photo_assets).where(
                    photo_assets.c.asset_id == asset_id,
                    photo_assets.c.state == AssetState.RESERVED.value,
                ).values(state=AssetState.STORED.value)
            )
            if result.rowcount != 1:
                raise PermissionError("Photo asset is not reserved")
            await session.commit()
