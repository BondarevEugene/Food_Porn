"""Aggregate-only retention history for privileged operational monitoring.

This table intentionally has no child ID, story ID, object key, free text,
exception message or personal identifiers.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

metadata = MetaData()
retention_runs = Table(
    "little_legend_retention_runs",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("checked_at", DateTime(timezone=True), nullable=False),
    Column("mode", String(16), nullable=False),
    Column("status", String(16), nullable=False),
    Column("codes", JSON, nullable=False),
    Column("expired_not_deleted", Integer, nullable=False),
    Column("pending_over_24h", Integer, nullable=False),
    Column("exhausted_retries", Integer, nullable=False),
    Column("deletion_failed", Integer, nullable=False),
    Column("physically_deleted", Integer, nullable=False),
    Column("notification_sent", Boolean, nullable=False),
    CheckConstraint(
        "expired_not_deleted >= 0 AND pending_over_24h >= 0 "
        "AND exhausted_retries >= 0 AND deletion_failed >= 0 "
        "AND physically_deleted >= 0",
        name="ck_ll_retention_run_counts",
    ),
    Index("ix_ll_retention_runs_checked_at", "checked_at"),
)

_ALLOWED = frozenset({
    "RETENTION_EXPIRED_BACKLOG",
    "RETENTION_PENDING_OVER_24H",
    "RETENTION_RETRY_EXHAUSTED",
    "RETENTION_DELETE_FAILED",
})


def safe_snapshot(result: Mapping[str, Any]) -> dict[str, Any]:
    """Allowlist aggregate metrics; never persist untrusted raw JSON."""
    audit = result["audit"]
    operations = result["operations"]
    status = operations["status"]
    if status not in {"ok", "warning", "critical"}:
        raise ValueError("Invalid retention status")
    codes = operations["codes"]
    if not isinstance(codes, (list, tuple)) or any(
        not isinstance(code, str) or code not in _ALLOWED for code in codes
    ):
        raise ValueError("Invalid retention alert codes")
    if len(codes) > len(_ALLOWED):
        raise ValueError("Too many alert codes")
    def count(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("Invalid aggregate count")
        return value
    return {
        "checked_at": datetime.now(UTC),
        "mode": "execute" if "retention" in result else "dry-run",
        "status": status,
        "codes": sorted(set(codes)),
        "expired_not_deleted": count(audit["expired_not_deleted"]),
        "pending_over_24h": count(audit["pending_over_24h"]),
        "exhausted_retries": count(audit["exhausted_retries"]),
        "deletion_failed": count(
            result.get("retention", {}).get("deletion_failed", 0)
        ),
        "physically_deleted": count(
            result.get("retention", {}).get("physically_deleted", 0)
        ),
        "notification_sent": result.get("notification", {}).get("sent") is True,
    }


async def record_retention_run(
    session: AsyncSession, result: Mapping[str, Any],
) -> None:
    await session.execute(insert(retention_runs).values(**safe_snapshot(result)))
    await session.commit()


async def recent_retention_runs(
    session: AsyncSession, *, limit: int = 20,
) -> list[dict[str, Any]]:
    """For authenticated admin handlers only. Never expose publicly."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    rows = (await session.execute(
        select(retention_runs)
        .order_by(retention_runs.c.checked_at.desc(), retention_runs.c.id.desc())
        .limit(limit)
    )).mappings().all()
    return [
        {
            **dict(row),
            "checked_at": row["checked_at"].isoformat(),
        }
        for row in rows
    ]
