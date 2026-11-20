"""Run a bounded, fail-closed paid-book production and Telegram delivery cycle.

Invoke via: python -m app.little_legend.paid_book_worker
Use a single Railway worker process with the same database and S3 credentials.
Ambiguous provider delivery is not retried automatically.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.database.session import async_session_maker
from app.little_legend.fulfillment_queue import fulfillment_jobs
from app.little_legend.order_quotes import order_quotes
from app.little_legend.paid_book_storage import PaidBookStore, pdf_key
from app.little_legend.payment_entitlement import has_verified_entitlement
from app.little_legend.production_leases import ProductionLease, claim_pending, heartbeat

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
    """Select paid pending work with SKIP LOCKED, then atomically fence it.

    No external work starts until the transaction commits.
    """
    async with async_session_maker() as session:
        row = (await session.execute(
            select(
                fulfillment_jobs.c.quote_id,
                fulfillment_jobs.c.owner_id,
                order_quotes.c.story_id,
            )
            .join(order_quotes, order_quotes.c.id == fulfillment_jobs.c.quote_id)
            .where(
                fulfillment_jobs.c.status == "pending",
                fulfillment_jobs.c.lease_token.is_(None),
                fulfillment_jobs.c.owner_id == order_quotes.c.owner_id,
            )
            .order_by(fulfillment_jobs.c.created_at)
            .with_for_update(of=fulfillment_jobs, skip_locked=True)
            .limit(1)
        )).mappings().one_or_none()
        if row is None:
            return None
        if not await has_verified_entitlement(
            session, quote_id=row["quote_id"], owner_id=row["owner_id"],
        ):
            await session.execute(
                update(fulfillment_jobs).where(
                    fulfillment_jobs.c.quote_id == row["quote_id"],
                    fulfillment_jobs.c.owner_id == row["owner_id"],
                    fulfillment_jobs.c.status == "pending",
                ).values(status="blocked", updated_at=datetime.now(UTC))
            )
            await session.commit()
            return None
        lease = await claim_pending(
            session, quote_id=row["quote_id"], owner_id=row["owner_id"],
        )
        if lease is None:
            await session.rollback()
            return None
        await session.commit()
        return {**dict(row), "lease": lease}


async def _keep_lease_alive(lease: ProductionLease, stop: asyncio.Event) -> None:
    """Extend the lease during S3/PDF work; never revive an expired lease."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=45)
            return
        except TimeoutError:
            pass
        async with async_session_maker() as session:
            alive = await heartbeat(session, lease=lease)
            if not alive:
                await session.rollback()
                logger.error("Little Legend production lease lost for %s", lease.quote_id)
                return
            await session.commit()


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
    from app.little_legend.production_readiness import assess_production

    decision = draft.editorial_decision
    approved = all((
        decision.hero_fidelity_reviewed,
        decision.age_appropriateness_reviewed,
        decision.narrative_continuity_reviewed,
        decision.parent_final_approval,
    ))
    readiness = assess_production(
        graph=draft.graph, manuscript=draft.manuscript,
        jobs=jobs, editorial_approved=approved,
    )
    if not readiness.ready_for_export:
        raise PermissionError("Approved manuscript, art and editorial gates required")
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
        edition="digital",
        palette=draft.palette,
    )
    key = pdf_key(quote_id=row["quote_id"], owner_id=row["owner_id"])
    await asyncio.to_thread(PaidBookStore().put, key=key, data=pdf)
    return key


async def _mark_ready(row: dict, key: str) -> bool:
    """Commit the private PDF key only while holding the live fencing token."""
    lease = row["lease"]
    async with async_session_maker() as session:
        result = await session.execute(
            update(fulfillment_jobs).where(
                fulfillment_jobs.c.quote_id == row["quote_id"],
                fulfillment_jobs.c.owner_id == row["owner_id"],
                fulfillment_jobs.c.status == "processing",
                fulfillment_jobs.c.lease_token == lease.token,
                fulfillment_jobs.c.lease_expires_at > datetime.now(UTC),
            ).values(
                status="ready", asset_key=key, lease_token=None,
                lease_expires_at=None, updated_at=datetime.now(UTC),
            ).returning(fulfillment_jobs.c.quote_id)
        )
        ok = result.scalar_one_or_none() is not None
        if ok:
            await session.commit()
        else:
            await session.rollback()
        return ok


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
                fulfillment_jobs.c.asset_key == key,
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
    """Run a paid, approved book; never auto-reclaim uncertain work."""
    if await _resume_ready_delivery():
        return True
    row = await _claim_one()
    if row is None:
        return False
    stop = asyncio.Event()
    keeper = asyncio.create_task(_keep_lease_alive(row["lease"], stop))
    try:
        key = await _render(row)
        # A stale worker may have completed an S3 upload. It must not
        # finalize the job or dispatch Telegram without a live lease.
        committed = await _mark_ready(row, key)
    except Exception:
        logger.exception("Little Legend production blocked for quote %s", row["quote_id"])
        async with async_session_maker() as session:
            await session.execute(
                update(fulfillment_jobs).where(
                    fulfillment_jobs.c.quote_id == row["quote_id"],
                    fulfillment_jobs.c.owner_id == row["owner_id"],
                    fulfillment_jobs.c.status == "processing",
                    fulfillment_jobs.c.lease_token == row["lease"].token,
                    fulfillment_jobs.c.lease_expires_at > datetime.now(UTC),
                ).values(
                    status="blocked", lease_token=None, lease_expires_at=None,
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()
        return True
    finally:
        stop.set()
        keeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await keeper
    if not committed:
        logger.error("Lease expired before PDF commit; manual review: %s", row["quote_id"])
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
