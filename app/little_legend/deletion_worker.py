"""Transactional object-deletion worker for Little Legend private media.

No scheduler is started here. A separate deployment must configure and invoke
this worker after reviewing bucket permissions, retention and monitoring.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.little_legend.object_store import ObjectStore, _validate_key
from app.little_legend.secure_vault import AssetState
from app.little_legend.vault_registry import vault_assets

logger = logging.getLogger(__name__)


def retry_delay(attempts: int) -> timedelta:
    """Exponential backoff capped at 24 hours, with no immediate retries."""
    if attempts < 1:
        raise ValueError("Attempt count must be positive")
    return timedelta(minutes=min(1440, 5 * 2 ** min(attempts - 1, 9)))


async def delete_pending_assets(
    session: AsyncSession,
    store: ObjectStore,
    *,
    batch_size: int = 50,
    now: datetime | None = None,
    on_error: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Delete objects then mark rows deleted; keep failed rows retryable.

    Callers MUST commit the session. Concurrent workers are serialized with
    PostgreSQL row locks; the transaction stays open during object deletion.
    A retry after a crash is safe with S3's idempotent delete semantics.
    """
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be 1..100")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    rows = (
        await session.execute(
            select(
                vault_assets.c.asset_id,
                vault_assets.c.object_key,
                vault_assets.c.deletion_attempts,
            )
            .where(
                vault_assets.c.state == AssetState.DELETION_PENDING.value,
                vault_assets.c.deletion_attempts < 8,
            )
            .order_by(vault_assets.c.expires_at, vault_assets.c.asset_id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    ).all()
    result = {"selected": len(rows), "deleted": 0, "failed": 0}
    for asset_id, key, attempts in rows:
        try:
            _validate_key(key)
            store.delete(key=key)
        except Exception:
            # Do not expose object key, provider response, child data or secrets.
            logger.warning("Little Legend private asset deletion failed", exc_info=False)
            if on_error is not None:
                on_error("OBJECT_DELETE_FAILED")
            await session.execute(
                update(vault_assets)
                .where(
                    vault_assets.c.asset_id == asset_id,
                    vault_assets.c.state == AssetState.DELETION_PENDING.value,
                )
                .values(
                    state=AssetState.DELETE_FAILED.value,
                    deletion_attempts=attempts + 1,
                    last_error_code="OBJECT_DELETE_FAILED",
                    last_deletion_attempt_at=instant,
                    next_deletion_attempt_at=instant + retry_delay(attempts + 1),
                )
            )
            result["failed"] += 1
        else:
            await session.execute(
                update(vault_assets)
                .where(
                    vault_assets.c.asset_id == asset_id,
                    vault_assets.c.state == AssetState.DELETION_PENDING.value,
                )
                .values(
                    state=AssetState.DELETED.value,
                    deleted_at=instant,
                    last_error_code=None,
                    last_deletion_attempt_at=instant,
                    next_deletion_attempt_at=None,
                )
            )
            result["deleted"] += 1
    return result
