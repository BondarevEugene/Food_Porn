"""Read-only Little Legend paid-order operational diagnostics.

No Telegram send, entitlement mutation or retry can be triggered here.
Run inside Railway shell with the existing application DATABASE_URL.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.database.session import async_session_maker
from app.little_legend.fulfillment_queue import fulfillment_jobs

STATES = frozenset({"pending", "processing", "blocked", "ready", "failed"})


def diagnose(row: dict, *, now: datetime) -> str:
    """Explain what an operator should check without changing order state."""
    if row["delivered_at"] is not None:
        return "delivered"
    if row["delivery_started_at"] is not None:
        return "telegram_delivery_requires_reconciliation"
    if row["status"] == "ready":
        return "ready_for_telegram"
    if row["status"] == "blocked":
        return "review_story_illustrations_or_storage"
    if row["status"] == "failed":
        return "manual_failure_review"
    if row["status"] == "processing":
        age = (now - row["updated_at"]).total_seconds()
        return "possibly_stalled_render" if age > 1800 else "render_in_progress"
    return "waiting_for_worker"


async def report(*, limit: int = 100) -> dict:
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        counts = (await session.execute(
            select(fulfillment_jobs.c.status, func.count())
            .group_by(fulfillment_jobs.c.status)
        )).all()
        rows = (await session.execute(
            select(
                fulfillment_jobs.c.quote_id,
                fulfillment_jobs.c.status,
                fulfillment_jobs.c.asset_key,
                fulfillment_jobs.c.created_at,
                fulfillment_jobs.c.updated_at,
                fulfillment_jobs.c.delivery_started_at,
                fulfillment_jobs.c.delivered_at,
            )
            .order_by(fulfillment_jobs.c.updated_at.desc())
            .limit(limit)
        )).mappings().all()
    return {
        "generated_at": now.isoformat(),
        "counts": {state: int(count) for state, count in counts},
        "orders": [
            {
                "quote_id": row["quote_id"],
                "status": row["status"],
                "has_pdf": row["asset_key"] is not None,
                "diagnosis": diagnose(dict(row), now=now),
                "updated_at": row["updated_at"].isoformat(),
            }
            for row in rows
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only paid-book operations")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(report(limit=args.limit)), indent=2))


if __name__ == "__main__":
    main()
