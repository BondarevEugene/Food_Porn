"""Periodic storage pressure checks using the existing bot Telegram session."""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from app.services.factory_alerts import FactoryAlertNotifier, disk_alert

logger = logging.getLogger(__name__)


class FactoryStorageMonitor:
    def __init__(self, bot, storage_root: Path, owner_ids: tuple[int, ...], interval_seconds: int = 900):
        if interval_seconds < 60:
            raise ValueError("Monitoring interval must be at least 60 seconds")
        self._bot = bot
        self._root = Path(storage_root)
        self._interval = interval_seconds
        self._notifier = FactoryAlertNotifier(self._send, owner_ids)
        self._task: asyncio.Task[None] | None = None

    async def _send(self, uid: int, message: str) -> object:
        return await self._bot.send_message(uid, message)

    async def check_once(self) -> int | None:
        try:
            total, used, _ = shutil.disk_usage(self._root)
            if not total:
                raise OSError("Disk capacity unknown")
            percent = round(100 * used / total)
            alert = disk_alert(percent)
            if alert:
                await self._notifier.notify(*alert)
            return percent
        except OSError:
            logger.exception("Storage pressure probe failed")
            await self._notifier.notify(
                "disk:unavailable", "⚠️ Food_Porn: storage monitoring unavailable. Check Railway and Mini CRM."
            )
            return None

    async def _loop(self) -> None:
        while True:
            try:
                await self.check_once()
            except Exception:
                logger.exception("Unexpected storage monitor error")
            await asyncio.sleep(self._interval)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="factory-storage-monitor")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
