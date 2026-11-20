"""Bounded, single-owner PostgreSQL retention orchestration.

The advisory lock is connection-scoped and held for the whole cleanup run.
Never schedule on SQLite or run two independent deletion loops.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.little_legend.vault_erasure_worker import PrivateObjectDeleter
from app.little_legend.vault_retention_cycle import run_private_retention_cycle

_LOCK_ID = 726489113042


@dataclass(frozen=True)
class DrainReport:
    status: str
    cycles: int
    expired_queued: int
    physically_deleted: int
    deletion_failed: int
    more_work_possible: bool


async def drain_retention(
    *, engine: AsyncEngine, deleter: PrivateObjectDeleter,
    batch_size: int = 25, max_cycles: int = 4,
) -> DrainReport:
    """Drain at most max_cycles, refusing concurrent runs via PG advisory lock."""
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be 1..100")
    if not 1 <= max_cycles <= 20:
        raise ValueError("max_cycles must be 1..20")
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Retention lock requires PostgreSQL")
    async with engine.connect() as conn:
        locked = bool((await conn.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": _LOCK_ID},
        )).scalar_one())
        if not locked:
            return DrainReport(
                status="already_running", cycles=0, expired_queued=0,
                physically_deleted=0, deletion_failed=0,
                more_work_possible=True,
            )
        try:
            totals = {"expired_queued": 0, "physically_deleted": 0,
                      "deletion_failed": 0}
            more = False
            cycles = 0
            for _ in range(max_cycles):
                report = await run_private_retention_cycle(
                    deleter=deleter, batch_size=batch_size,
                )
                cycles += 1
                for key in totals:
                    totals[key] += getattr(report, key)
                more = report.more_work_possible
                if not more:
                    break
                if not report.expired_queued and not report.physically_deleted:
                    break
            return DrainReport(
                status="completed", cycles=cycles,
                more_work_possible=more, **totals,
            )
        finally:
            await conn.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": _LOCK_ID},
            )


def drain_to_dict(report: DrainReport) -> dict[str, Any]:
    return asdict(report)
