"""Run a bounded, fail-closed paid-book production and Telegram delivery cycle.

Invoke via: python -m app.little_legend.paid_book_worker
Use a single Railway worker process with the same database and S3 credentials.
Ambiguous provider delivery is not retried automatically.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.database.session import async_session_maker
from app.little_legend.fulfillment_queue import fulfillment_jobs
from app.little_legend.order_quotes import order_quotes
from app.little_legend.paid_book_storage import PaidBookStore, pdf_key
from app.little_legend.payment_entitlement import has_verified_entitlement

logger = logging.getLogger(__name__)


def _illustration_store():
    from app.little_legend.generated_art_store import (
        GeneratedArtS3Settings,
        S3GeneratedArtStore,
    )

    return S3GeneratedArtStore(GeneratedArtS3Settings(
        endpoint_url=os.getenv("LITTLE_LEGEND_ART_S3_ENDPOINT", ""),
        bucket=os.getenv("LITTLE_LEGEND_ART_S3_BUCKET", ""),
        region=os.getenv("LITTLE_LEGEND_ART_S3_REGION", ""),
        access_key_id=os.getenv("LITTLE_LEGEND_ART_S3_ACCESS_KEY", ""),
        secret_access_key=os.getenv("LITTLE_LEGEND_ART_S3_SECRET_KEY", ""),
    ))


async def _claim_one() -> dict | None:
    """Commit the claim before any expensive S3 or PDF work."""
    async with async_session_maker() as session:
        row = (await session.execute(
            select(
                fulfillment_jobs.c.quote_id,
                fulfillment_jobs.c.owner_id,
                order_quotes.c.story_id,
            )
            .join(order_quotes, order_quotes.c.id == fulfillment_jobs.c.quote_id)
            .where(fulfillment_jobs.c.status == "pending")
            .order_by(fulfillment_jobs.c.created_at)
            .with_for_update(of=fulfillment_jobs, skip_locked=True)
            .limit(1)
        )).mappings().one_or_none()
        if row is None:
            return None
        if not await has_verified_entitlement(
            session, quote_id=row["quote_id"], owner_id=row["owner_id"]
        ):
            await session.execute(
                update(fulfillment_jobs)
                .where(fulfillment_jobs.c.quote_id == row["quote_id"])
                .values(status="blocked", updated_at=datetime.now(UTC))
            )
            await session.commit()
            return None
        await session.execute(
            update(fulfillment_jobs)
            .where(fulfillment_jobs.c.quote_id == row["quote_id"])
            .values(status="processing", updated_at=datetime.now(UTC))
        )
        await session.commit()
        return dict(row)


async def _render(row: dict) -> str:
    from app.little_legend.illustration_queue_store import list_owner_illustration_jobs
    from app.little_legend.router import StoryDraft, stories
    from app.little_legend.stored_book_proof import assemble_stored_book_proof

    async with async_session_maker() as session:
        raw = await session.scalar(
            select(stories.c.data).where(
                stories.c.id == row["story_id"],
                stories.c.owner_id == row["owner_id"],
            )
        )
    if raw is None:
        raise PermissionError("Story was deleted")
    draft = StoryDraft.model_validate_json(raw)
    if draft.graph is None or draft.manuscript is None:
        raise PermissionError("Story is incomplete")
    jobs = await list_owner_illustration_jobs(
        story_id=row["story_id"], owner_id=row["owner_id"]
    )
    # The existing renderer enforces approved, revision-matched prose and art.
    pdf = await asyncio.to_thread(
        assemble_stored_book_proof,
        store=_illustration_store(),
        owner_id=row["owner_id"],
        story_id=row["story_id"],
        title=draft.title,
        dedication=draft.dedication,
        graph=draft.graph,
        manuscript=draft.manuscript,
        jobs=jobs,
    )
    key = pdf_key(quote_id=row["quote_id"], owner_id=row["owner_id"])
    await asyncio.to_thread(PaidBookStore().put, key=key, data=pdf)
    return key


async def _mark_ready(row: dict, key: str) -> None:
    async with async_session_maker() as session:
        await session.execute(
            update(fulfillment_jobs)
            .where(
                fulfillment_jobs.c.quote_id == row["quote_id"],
                fulfillment_jobs.c.owner_id == row["owner_id"],
                fulfillment_jobs.c.status == "processing",
            )
            .values(status="ready", asset_key=key, updated_at=datetime.now(UTC))
        )
        await session.commit()


async def _deliver(row: dict, key: str) -> None:
    # Claim delivery BEFORE the external Telegram side effect. If Railway
    # crashes after dispatch, an operator must reconcile; never send twice.
    async with async_session_maker() as session:
        result = await session.execute(
            update(fulfillment_jobs)
            .where(
                fulfillment_jobs.c.quote_id == row["quote_id"],
                fulfillment_jobs.c.owner_id == row["owner_id"],
                fulfillment_jobs.c.status == "ready",
                fulfillment_jobs.c.delivery_started_at.is_(None),
            )
            .values(delivery_started_at=datetime.now(UTC))
            .returning(fulfillment_jobs.c.quote_id)
        )
        if result.scalar_one_or_none() is None:
            await session.rollback()
            return
        await session.commit()
    await _send_claimed_delivery(row, key)

async def _resume_ready_delivery() -> bool:
    """Resume saved PDF delivery after a crash before Telegram dispatch.

    Never resend a job whose delivery_started_at was already persisted:
    Telegram may have accepted that message even if the worker crashed.
    """
    async with async_session_maker() as session:
        row = (await session.execute(
            select(
                fulfillment_jobs.c.quote_id,
                fulfillment_jobs.c.owner_id,
                fulfillment_jobs.c.asset_key,
                order_quotes.c.story_id,
            )
            .join(order_quotes, order_quotes.c.id == fulfillment_jobs.c.quote_id)
            .where(
                fulfillment_jobs.c.status == "ready",
                fulfillment_jobs.c.asset_key.is_not(None),
                fulfillment_jobs.c.delivery_started_at.is_(None),
            )
            .order_by(fulfillment_jobs.c.updated_at)
            .with_for_update(of=fulfillment_jobs, skip_locked=True)
            .limit(1)
        )).mappings().one_or_none()
        if row is None:
            return False
        if not await has_verified_entitlement(
            session, quote_id=row["quote_id"], owner_id=row["owner_id"]
        ):
            await session.execute(
                update(fulfillment_jobs)
                .where(fulfillment_jobs.c.quote_id == row["quote_id"])
                .values(status="blocked", updated_at=datetime.now(UTC))
            )
            await session.commit()
            return True
        # Reserve the Telegram send before releasing the row lock.
        await session.execute(
            update(fulfillment_jobs)
            .where(fulfillment_jobs.c.quote_id == row["quote_id"])
            .values(delivery_started_at=datetime.now(UTC))
        )
        await session.commit()
    try:
        await _send_claimed_delivery(dict(row), row["asset_key"])
    except Exception:
        logger.exception(
            "Little Legend delivery requires manual reconciliation: %s",
            row["quote_id"],
        )
    return True


async def _send_claimed_delivery(row: dict, key: str) -> None:
    """Send a pre-claimed delivery; no automatic retry on ambiguity."""
    from aiogram import Bot
    from aiogram.types import BufferedInputFile

    from app.config import get_settings

    pdf = await asyncio.to_thread(PaidBookStore().get, key=key)
    bot = Bot(token=get_settings().bot_token)
    try:
        await bot.send_document(
            chat_id=row["owner_id"],
            document=BufferedInputFile(
                pdf, filename=f"little-legend-{row['quote_id']}.pdf"
            ),
            caption="Ваша книга Little Legend готова!",
        )
    finally:
        await bot.session.close()
    async with async_session_maker() as session:
        await session.execute(
            update(fulfillment_jobs)
            .where(
                fulfillment_jobs.c.quote_id == row["quote_id"],
                fulfillment_jobs.c.owner_id == row["owner_id"],
                fulfillment_jobs.c.status == "ready",
                fulfillment_jobs.c.delivered_at.is_(None),
            )
            .values(
                delivered_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def process_one() -> bool:
    """Process one paid book; failures are persisted and never silently retried."""
    if await _resume_ready_delivery():
        return True
    row = await _claim_one()
    if row is None:
        return False
    try:
        key = await _render(row)
        await _mark_ready(row, key)
    except Exception:
        logger.exception("Little Legend production blocked for quote %s", row["quote_id"])
        async with async_session_maker() as session:
            await session.execute(
                update(fulfillment_jobs)
                .where(
                    fulfillment_jobs.c.quote_id == row["quote_id"],
                    fulfillment_jobs.c.status == "processing",
                )
                .values(status="blocked", updated_at=datetime.now(UTC))
            )
            await session.commit()
        return True
    try:
        await _deliver(row, key)
    except Exception:
        logger.exception("Little Legend delivery needs reconciliation: %s", row["quote_id"])
    return True


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        worked = await process_one()
        if not worked:
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
