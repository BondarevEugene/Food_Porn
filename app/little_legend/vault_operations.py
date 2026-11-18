"""Operational retention cycle for Little Legend private media.

Opt-in only. No background task is started on import or application boot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.little_legend.deletion_worker import delete_pending_assets
from app.little_legend.object_store import ObjectStore
from app.little_legend.secure_vault import AssetState
from app.little_legend.vault_registry import request_expired_deletions, vault_assets


class StoreFactory(Protocol):
    def __call__(self) -> ObjectStore: ...


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
    """Retry previously failed deletions only after a bounded cooldown.

    The current schema has no last-attempt timestamp, so a safe cooldown
    cannot be computed yet. Fail closed rather than retrying in a hot loop.
    """
    if not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be 1..500")
    if retry_after < timedelta(minutes=1):
        raise ValueError("Retry interval must be at least one minute")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    return 0


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

    async with session_factory() as session, session.begin():
        queued = await request_expired_deletions(
            session, now=instant, batch_size=batch_size
        )

    async with session_factory() as session, session.begin():
        outcome = await delete_pending_assets(
            session, store, now=instant, batch_size=batch_size
        )

    async with session_factory() as session:
        health = await retention_health(session, now=instant)

    return RetentionReport(
        queued=len(queued),
        retried=0,
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
            .select_from(__import__(
                "app.little_legend.vault_registry", fromlist=["stories_table"]
            ).stories_table)
            .where(
                __import__(
                    "app.little_legend.vault_registry", fromlist=["stories_table"]
                ).stories_table.c.id == story_id,
                __import__(
                    "app.little_legend.vault_registry", fromlist=["stories_table"]
                ).stories_table.c.owner_id == owner_id,
            )
            .exists(),
        )
        .values(state=AssetState.DELETION_PENDING.value)
    )
    return result.rowcount
