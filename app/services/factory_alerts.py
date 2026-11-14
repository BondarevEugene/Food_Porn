"""Deduplicated owner-only Telegram infrastructure alerts.

Designed to be called by health probes and workers. Does not claim to detect
complete process outages; those require an external heartbeat observer.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class FactoryAlertNotifier:
    def __init__(
        self,
        send: Callable[[int, str], Awaitable[object]],
        owner_ids: tuple[int, ...],
        *,
        cooldown_seconds: int = 1800,
    ) -> None:
        if cooldown_seconds < 60:
            raise ValueError("Alert cooldown must be at least one minute")
        self._send = send
        self._owners = tuple(uid for uid in dict.fromkeys(owner_ids) if uid > 0)
        self._cooldown = cooldown_seconds
        self._last_sent: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def notify(self, key: str, message: str) -> bool:
        """Send once per key/cooldown; failed delivery remains retryable."""
        if not key or not message or not self._owners:
            return False
        async with self._lock:
            now = time.monotonic()
            if now - self._last_sent.get(key, float("-inf")) < self._cooldown:
                return False
            delivered = False
            for uid in self._owners:
                try:
                    await self._send(uid, message[:3500])
                    delivered = True
                except Exception:
                    logger.exception("Infrastructure alert delivery failed for owner %s", uid)
            if delivered:
                self._last_sent[key] = now
            return delivered


def disk_alert(used_percent: int) -> tuple[str, str] | None:
    """Map actual filesystem pressure to a stable alert key and message."""
    if not 0 <= used_percent <= 100:
        raise ValueError("Disk usage must be between 0 and 100")
    if used_percent >= 95:
        level = "critical"
    elif used_percent >= 85:
        level = "high"
    elif used_percent >= 70:
        level = "warning"
    else:
        return None
    return ("disk:" + level, f"⚠️ Food_Porn: disk usage {used_percent}% ({level}). Open Mini CRM → Factory.")
