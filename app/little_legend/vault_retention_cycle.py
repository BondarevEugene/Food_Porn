"""Explicit operator-run retention cycle for private child-media metadata.

No background scheduler is started automatically and photo upload remains off.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.database.session import async_session_maker
from app.little_legend.vault_erasure_worker import (
    PrivateObjectDeleter,
    erase_due_private_assets,
)
from app.little_legend.vault_registry import request_expired_deletions


@dataclass(frozen=True)
class RetentionCycleReport:
    expired_queued: int
    physically_deleted: int
    deletion_failed: int
    more_work_possible: bool
    completed_at: datetime


async def run_private_retention_cycle(
    *, deleter: PrivateObjectDeleter, batch_size: int = 25,
    now: datetime | None = None,
) -> RetentionCycleReport:
    """Queue expired assets, then attempt physical deletion.

    The queueing transaction commits BEFORE object deletion, so a crash
    cannot silently lose a retention deadline. No completion is claimed
    for objects still pending, failed or requiring operator reconciliation.
    """
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be 1..100")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    async with async_session_maker() as session:
        expired = await request_expired_deletions(
            session, now=instant, batch_size=batch_size,
        )
        await session.commit()
    results = await erase_due_private_assets(
        deleter=deleter, batch_size=batch_size, now=instant,
    )
    return RetentionCycleReport(
        expired_queued=len(expired),
        physically_deleted=results["deleted"],
        deletion_failed=results["failed"],
        more_work_possible=(
            len(expired) >= batch_size
            or results["deleted"] + results["failed"] >= batch_size
        ),
        completed_at=instant,
    )
