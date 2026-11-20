"""PostgreSQL-backed retention alert suppression and delivery leases.

One global scope for aggregate-only owner notifications. No private asset data.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import Column, DateTime, MetaData, String, Table, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

metadata = MetaData()
alert_state = Table(
    "little_legend_retention_alert_state",
    metadata,
    Column("scope", String(32), primary_key=True),
    Column("fingerprint", String(64), nullable=False),
    Column("lease_token", String(36)),
    Column("leased_until", DateTime(timezone=True)),
    Column("last_sent_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
_SCOPE = "owner_retention"
_COOLDOWN = timedelta(hours=6)
_LEASE = timedelta(minutes=2)


@dataclass(frozen=True)
class AlertClaim:
    token: str | None
    reason: str


def alert_fingerprint(status: str, codes: tuple[str, ...] | list[str]) -> str:
    """Hash aggregate severity/codes only, never arbitrary input."""
    if status not in {"warning", "critical"}:
        raise ValueError("Invalid alert severity")
    from app.little_legend.retention_notifications import alert_message

    alert_message({"status": status, "codes": codes})
    raw = json.dumps([status, sorted(set(codes))], separators=(",", ":"))
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


async def claim_alert(
    session: AsyncSession, *, fingerprint: str,
    now: datetime | None = None,
) -> AlertClaim:
    """Atomically reserve delivery across workers. Commit before network I/O."""
    if len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
        raise ValueError("Invalid fingerprint")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    await session.execute(
        pg_insert(alert_state).values(
            scope=_SCOPE, fingerprint="", updated_at=instant,
        ).on_conflict_do_nothing(index_elements=["scope"])
    )
    row = (await session.execute(
        select(alert_state).where(alert_state.c.scope == _SCOPE)
        .with_for_update()
    )).mappings().one()
    if row["lease_token"] and row["leased_until"] and row["leased_until"] > instant:
        await session.commit()
        return AlertClaim(None, "delivery_in_progress")
    if (
        row["fingerprint"] == fingerprint
        and row["last_sent_at"] is not None
        and row["last_sent_at"] > instant - _COOLDOWN
    ):
        await session.commit()
        return AlertClaim(None, "cooldown")
    token = str(uuid4())
    await session.execute(
        update(alert_state).where(alert_state.c.scope == _SCOPE).values(
            fingerprint=fingerprint,
            lease_token=token,
            leased_until=instant + _LEASE,
            updated_at=instant,
        )
    )
    await session.commit()
    return AlertClaim(token, "claimed")


async def finish_alert(
    session: AsyncSession, *, token: str, sent: bool,
    now: datetime | None = None,
) -> None:
    """Complete only the matching lease; a stale worker cannot overwrite it."""
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    values = {
        "lease_token": None, "leased_until": None, "updated_at": instant,
    }
    if sent:
        values["last_sent_at"] = instant
    await session.execute(
        update(alert_state).where(
            alert_state.c.scope == _SCOPE,
            alert_state.c.lease_token == token,
        ).values(**values)
    )
    await session.commit()


async def clear_alert_after_recovery(
    session: AsyncSession, *, now: datetime | None = None,
) -> None:
    """Reset cooldown after a healthy check, unless delivery is in progress."""
    instant = now or datetime.now(UTC)
    await session.execute(
        update(alert_state).where(
            alert_state.c.scope == _SCOPE,
            (
                alert_state.c.lease_token.is_(None)
                | (alert_state.c.leased_until <= instant)
            ),
        ).values(
            fingerprint="", last_sent_at=None,
            lease_token=None, leased_until=None, updated_at=instant,
        )
    )
    await session.commit()


async def alert_delivery_status(session: AsyncSession) -> dict[str, object]:
    """Aggregate alert status for owner-only CRM. No tokens or fingerprints."""
    row = (await session.execute(
        select(
            alert_state.c.last_sent_at,
            alert_state.c.leased_until,
        ).where(alert_state.c.scope == _SCOPE)
    )).one_or_none()
    now = datetime.now(UTC)
    if row is None:
        return {"configured": False, "in_progress": False, "last_sent_at": None}
    return {
        "configured": True,
        "in_progress": bool(row.leased_until and row.leased_until > now),
        "last_sent_at": (
            row.last_sent_at.isoformat() if row.last_sent_at else None
        ),
    }
