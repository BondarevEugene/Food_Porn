"""Physical erasure and retention for the NEW Neon photo asset registry.

This is separate from the legacy little_legend_vault_assets registry.
The R2 object is deleted before the database row is marked DELETED.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.session import async_session_maker
from app.little_legend.neon_photo_vault import photo_assets
from app.little_legend.private_photo_vault import PrivatePhotoObjectStore
from app.little_legend.secure_vault import AssetState

MAX_ATTEMPTS = 8


def _due(row: dict, now: datetime) -> bool:
    if row["state"] in (AssetState.RESERVED.value, AssetState.STORED.value):
        return row["expires_at"] <= now
    if row["state"] in (
        AssetState.DELETION_PENDING.value, AssetState.DELETE_FAILED.value,
    ):
        attempts = row["deletion_attempts"]
        if attempts >= MAX_ATTEMPTS:
            return False
        return row["expires_at"] <= now
    return False


async def erase_expired_photo_assets(
    *, objects: PrivatePhotoObjectStore,
    batch_size: int = 25,
    now: datetime | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, int]:
    """Process expired and previously failed assets without double-processing rows.

    Holds a row lock during deletion. A crash leaves the object eligible for
    another attempt; S3 DeleteObject must be idempotent for missing keys.
    """
    if not 1 <= batch_size <= 100:
        raise ValueError("Invalid photo erasure batch size")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Timezone-aware erasure timestamp required")
    result = {"deleted": 0, "failed": 0}
    seen: set[str] = set()
    factory = session_factory or async_session_maker
    for _ in range(batch_size):
        async with factory() as session:
            rows = (await session.execute(
                select(photo_assets).where(
                    photo_assets.c.asset_id.not_in(seen),
                    photo_assets.c.state != AssetState.DELETED.value,
                ).order_by(
                    photo_assets.c.expires_at, photo_assets.c.asset_id,
                ).limit(batch_size).with_for_update(skip_locked=True)
            )).mappings().all()
            due = next((row for row in rows if _due(row, instant)), None)
            if due is None:
                break
            asset_id = due["asset_id"]
            seen.add(asset_id)
            key = due["object_key"]
            if key != "little-legend/private/" + asset_id:
                raise PermissionError("Invalid photo asset key")
            try:
                await asyncio.to_thread(objects.delete, key=key)
            except Exception:
                attempts = due["deletion_attempts"] + 1
                await session.execute(update(photo_assets).where(
                    photo_assets.c.asset_id == asset_id,
                ).values(
                    state=AssetState.DELETE_FAILED.value,
                    deletion_attempts=attempts,
                    last_error_code="storage_delete_failed",
                ))
                result["failed"] += 1
            else:
                await session.execute(update(photo_assets).where(
                    photo_assets.c.asset_id == asset_id,
                ).values(
                    state=AssetState.DELETED.value,
                    deleted_at=instant,
                    deletion_attempts=due["deletion_attempts"] + 1,
                    last_error_code=None,
                ))
                result["deleted"] += 1
            await session.commit()
    return result
