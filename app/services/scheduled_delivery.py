"""
==========================================================
FOOD_PORN

Module: Scheduled Gift Delivery Worker
Layer: Service
==========================================================
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import ScheduledDelivery
from app.services.email_service import send_ready_order_email

logger = logging.getLogger(__name__)


class ScheduledDeliveryWorker:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], interval: int = 30) -> None:
        self.session_factory = session_factory
        self.interval = interval
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="scheduled-gift-delivery")

    async def stop(self) -> None:
        if self._task:
            self._stop.set()
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_due()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduled delivery cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except TimeoutError:
                pass

    async def run_due(self) -> int:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(ScheduledDelivery)
                    .where(
                        ScheduledDelivery.status == "pending",
                        ScheduledDelivery.send_at <= now,
                    )
                    .order_by(ScheduledDelivery.send_at)
                    .limit(20)
                )
            ).scalars().all()
            sent = 0
            for row in rows:
                row.attempts += 1
                paths = [Path(value) for value in row.attachments]
                if not paths or not all(path.is_file() for path in paths):
                    row.status = "failed"
                    row.error_message = "One or more attachments are unavailable"
                    continue
                try:
                    await send_ready_order_email(row.recipient_email, row.subject, paths)
                    row.status = "sent"
                    row.sent_at = datetime.now(UTC)
                    row.error_message = None
                    sent += 1
                except Exception as exc:
                    row.error_message = f"{type(exc).__name__}: {exc}"[:1000]
                    if row.attempts >= 3:
                        row.status = "failed"
                    logger.exception("Scheduled delivery %s failed", row.id)
            await session.commit()
            return sent
