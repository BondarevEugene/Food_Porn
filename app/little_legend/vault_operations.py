"""Operational retention cycle for Little Legend private media.

Opt-in only. No background task is started on import or application boot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.little_legend.object_store import ObjectStore
from app.little_legend.secure_vault import AssetState
from app.little_legend.vault_registry import (
    request_expired_deletions,
    stories_table,
    vault_assets,
)


@dataclass(frozen=True)
class RetentionReport:
    queued: int
    retried: int
    deleted: int
    failed: int
    pending: int
    oldest_pending_seconds: int | None


async def requeue_failed_deletions(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    retry_after: timedelta = timedelta(minutes=30),
    batch_size: int = 100,
) -> int:
    """Requeue failed deletions when their durable retry timestamp is due."""
    if not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be 1..500")
    if retry_after < timedelta(minutes=1):
        raise ValueError("Retry interval must be at least one minute")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    result = await session.execute(
        update(vault_assets)
        .where(
            vault_assets.c.asset_id.in_(
                select(vault_assets.c.asset_id)
                .where(
                    vault_assets.c.state == AssetState.DELETE_FAILED.value,
                    vault_assets.c.deletion_attempts < 8,
                    vault_assets.c.next_deletion_attempt_at.is_not(None),
                    vault_assets.c.next_deletion_attempt_at <= instant,
                    vault_assets.c.last_deletion_attempt_at <= instant - retry_after,
                )
                .order_by(vault_assets.c.next_deletion_attempt_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        .values(
            state=AssetState.DELETION_PENDING.value,
            next_deletion_attempt_at=None,
        )
    )
    return result.rowcount


async def retention_health(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int | None]:
    """Aggregate-only health, with no object keys or user identifiers."""
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    pending_states = (
        AssetState.DELETION_PENDING.value,
        AssetState.DELETE_FAILED.value,
    )
    pending, earliest = (
        await session.execute(
            select(func.count(), func.min(vault_assets.c.expires_at))
            .where(vault_assets.c.state.in_(pending_states))
        )
    ).one()
    age = (
        max(0, int((instant - earliest).total_seconds()))
        if earliest is not None else None
    )
    return {"pending": pending, "oldest_pending_seconds": age}


async def run_retention_cycle(
    session_factory: async_sessionmaker[AsyncSession],
    store: ObjectStore,
    *,
    now: datetime | None = None,
    batch_size: int = 50,
) -> RetentionReport:
    """Queue expired assets, commit, delete, commit, then read health.

    Failures in storage are recorded as DELETE_FAILED. Unexpected database
    errors propagate to the caller; no false success report is returned.
    """
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be 1..100")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")

    # Single canonical deletion worker: legacy store is adapted to the
    # confirmed, row-locked erasure worker. Do not run two independent paths.
    from app.little_legend.vault_erasure_worker import erase_due_private_assets

    class _LegacyStoreAdapter:
        def delete_private_object(self, *, object_key: str) -> None:
            store.delete(key=object_key)

    async with session_factory() as session, session.begin():
        retried = 0  # Canonical worker handles due DELETE_FAILED rows directly.
        queued = await request_expired_deletions(
            session, now=instant, batch_size=batch_size
        )

    outcome = await erase_due_private_assets(
        deleter=_LegacyStoreAdapter(), batch_size=batch_size, now=instant,
        session_factory=session_factory,
    )

    async with session_factory() as session:
        health = await retention_health(session, now=instant)

    return RetentionReport(
        queued=len(queued),
        retried=retried,
        deleted=outcome["deleted"],
        failed=outcome["failed"],
        pending=int(health["pending"]),
        oldest_pending_seconds=health["oldest_pending_seconds"],
    )


async def queue_story_deletion(
    session: AsyncSession, *, owner_id: int, story_id: int
) -> int:
    """Owner-scoped deletion request for consent withdrawal or story erasure.

    This queues object deletion; it does not claim physical erasure.
    """
    if owner_id <= 0 or story_id <= 0:
        raise ValueError("Invalid owner or story")
    eligible = (
        AssetState.RESERVED.value,
        AssetState.STORED.value,
        AssetState.DELETE_FAILED.value,
    )
    result = await session.execute(
        update(vault_assets)
        .where(
            vault_assets.c.owner_id == owner_id,
            vault_assets.c.story_id == story_id,
            vault_assets.c.state.in_(eligible),
            select(1)
            .select_from(stories_table)
            .where(
                stories_table.c.id == story_id,
                stories_table.c.owner_id == owner_id,
            )
            .exists(),
        )
        .values(state=AssetState.DELETION_PENDING.value)
    )
    return result.rowcount
