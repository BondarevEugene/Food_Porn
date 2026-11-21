"""Non-destructive storage preflight audit summaries.

Object keys may include customer information; only keyed hashes are persisted.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crm.models import Audit

ACTION = "storage.preflight"


def summarize_check(
    *,
    bot_id: str,
    provider: str,
    keys: list[str],
    outcome: str,
    secret: str,
    total_bytes: int | None = None,
) -> dict[str, Any]:
    if not secret:
        raise ValueError("Audit signing key is not configured")
    fingerprints = [
        hmac.new(secret.encode(), key.encode(), hashlib.sha256).hexdigest()
        for key in keys
    ]
    return {
        "bot_id": bot_id,
        "provider": provider,
        "count": len(keys),
        "fingerprints": fingerprints,
        "outcome": outcome,
        "total_bytes": total_bytes,
        "destructive": False,
    }


async def history(session: AsyncSession, *, limit: int = 30) -> list[dict[str, Any]]:
    if not 1 <= limit <= 100:
        raise ValueError("Invalid audit history limit")
    rows = (await session.execute(
        select(Audit).where(Audit.action == ACTION)
        .order_by(Audit.created_at.desc(), Audit.id.desc()).limit(limit)
    )).scalars().all()
    return [
        {
            "id": row.id,
            "actor": row.actor,
            "created_at": row.created_at.isoformat(),
            "bot_id": row.details.get("bot_id"),
            "provider": row.details.get("provider"),
            "count": row.details.get("count"),
            "outcome": row.details.get("outcome"),
            "total_bytes": row.details.get("total_bytes"),
        }
        for row in rows
    ]
