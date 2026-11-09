"""Bounded temporary MP4 retention; payment records are never deleted."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.database.models import VideoStoryOrder

logger = logging.getLogger(__name__)
MAX_VIDEOS = 30
MAX_AGE = timedelta(hours=24)
CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60


async def prune_video_archive(session_factory, *, now: datetime | None = None) -> int:
    """Keep at most 30 ready videos and expire them 24 hours after completion."""
    now = now or datetime.now(UTC)
    removed = 0
    async with session_factory() as session:
        rows = (await session.scalars(
            select(VideoStoryOrder)
            .where(VideoStoryOrder.output_path.is_not(None), VideoStoryOrder.status == "ready")
            .order_by(VideoStoryOrder.updated_at.desc(), VideoStoryOrder.id.desc())
        )).all()
        for index, order in enumerate(rows):
            updated = order.updated_at
            if updated is not None and updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            expired = updated is None or updated <= now - MAX_AGE
            if not expired and index < MAX_VIDEOS:
                continue
            path = Path(order.output_path)
            if (path.parent.name != "video_orders" or path.suffix.lower() != ".mp4"
                    or path.name != f"video_story_{order.id}.mp4"):
                logger.warning("Skipping unexpected video path for order %s", order.id)
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not remove expired video for order %s", order.id)
                continue
            order.output_path = None
            removed += 1
        await session.commit()
    return removed


class VideoRetentionWorker:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="video-retention")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                removed = await prune_video_archive(self.session_factory)
                if removed:
                    logger.info("Video retention removed %s temporary MP4 files", removed)
            except Exception:
                logger.exception("Video retention cleanup failed")
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
