"""Private vault erasure worker: physical deletion before metadata confirmation.

This does NOT enable child-photo uploads or provider processing. An operator
must explicitly configure the private object store and schedule the worker.
"""
from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select, update

from app.database.session import async_session_maker
from app.little_legend.secure_vault import AssetState
from app.little_legend.vault_registry import vault_assets

_MAX_ATTEMPTS = 8


class PrivateObjectDeleter(Protocol):
    def delete_private_object(self, *, object_key: str) -> None: ...


def validate_private_key(key: str) -> None:
    """Never allow arbitrary keys or paths to reach the deletion backend."""
    if not re.fullmatch(r"little-legend/private/[0-9a-f]{48}", key):
        raise PermissionError("Invalid private vault object key")


def retry_delay(attempts: int) -> timedelta:
    """Exponential backoff, capped at 24 hours."""
    if attempts < 1:
        raise ValueError("Attempt count must be positive")
    return timedelta(minutes=min(2 ** min(attempts, 11), 1440))


def error_category(exc: Exception) -> str:
    """Only a generic error code is persisted, never a sensitive exception."""
    if isinstance(exc, PermissionError):
        return "access_denied"
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return "storage_unavailable"
    return "deletion_failed"


async def erase_due_private_assets(
    *, deleter: PrivateObjectDeleter, batch_size: int = 25,
    now: datetime | None = None,
) -> dict[str, int]:
    """Delete due objects; keep metadata pending until storage confirms erasure.

    Claims one row at a time under a PostgreSQL row lock. A crash before
    physical deletion leaves the row pending and safe to retry. The deleter
    MUST treat a missing object as successful deletion.
    """
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be between 1 and 100")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    summary = {"deleted": 0, "failed": 0}
    # Process one locked row per transaction. The lock remains held while
    # the storage deletion is in flight to prevent two workers racing.
    for _ in range(batch_size):
        async with async_session_maker() as session:
            row = (await session.execute(
                select(vault_assets).where(
                    vault_assets.c.state.in_([
                        AssetState.DELETION_PENDING.value,
                        AssetState.DELETE_FAILED.value,
                    ]),
                    vault_assets.c.deletion_attempts < _MAX_ATTEMPTS,
                    (
                        (vault_assets.c.next_deletion_attempt_at.is_(None))
                        | (vault_assets.c.next_deletion_attempt_at <= instant)
                    ),
                ).order_by(
                    vault_assets.c.expires_at, vault_assets.c.asset_id,
                ).limit(1).with_for_update(skip_locked=True)
            )).mappings().first()
            if row is None:
                break
            key = row["object_key"]
            attempts = row["deletion_attempts"] + 1
            try:
                validate_private_key(key)
                await asyncio.to_thread(
                    deleter.delete_private_object, object_key=key,
                )
            except Exception as exc:
                await session.execute(
                    update(vault_assets).where(
                        vault_assets.c.asset_id == row["asset_id"],
                    ).values(
                        state=AssetState.DELETE_FAILED.value,
                        deletion_attempts=attempts,
                        last_error_code=error_category(exc),
                        last_deletion_attempt_at=instant,
                        next_deletion_attempt_at=instant + retry_delay(attempts),
                    )
                )
                summary["failed"] += 1
            else:
                await session.execute(
                    update(vault_assets).where(
                        vault_assets.c.asset_id == row["asset_id"],
                    ).values(
                        state=AssetState.DELETED.value,
                        deleted_at=instant,
                        deletion_attempts=attempts,
                        last_error_code=None,
                        last_deletion_attempt_at=instant,
                        next_deletion_attempt_at=None,
                    )
                )
                summary["deleted"] += 1
            await session.commit()
    return summary


class S3PrivateObjectDeleter:
    """Inject a private S3 client; no public URLs or object downloads."""

    def __init__(self, *, client: object, bucket: str) -> None:
        if not bucket.strip():
            raise ValueError("Private bucket is required")
        self.client = client
        self.bucket = bucket

    def delete_private_object(self, *, object_key: str) -> None:
        validate_private_key(object_key)
        self.client.delete_object(Bucket=self.bucket, Key=object_key)
