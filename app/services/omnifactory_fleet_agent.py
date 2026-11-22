"""Opt-in signed OmniFactory CRM heartbeat publisher.

The agent is outbound-only: it never exposes a management endpoint, bot token,
customer records or payment credentials. Disabled unless explicitly configured.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FleetAgentConfig:
    base_url: str = ""
    bot_key: str = ""
    ingest_secret: str = ""
    interval_seconds: int = 60
    runtime_version: str = "food-porn"

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.bot_key and self.ingest_secret)

    def validate(self) -> None:
        if not self.enabled:
            if self.base_url or self.bot_key or self.ingest_secret:
                raise ValueError("Fleet agent requires URL, bot key and secret together")
            return
        if not self.base_url.startswith("https://") or "@" in self.base_url:
            raise ValueError("Fleet agent requires a public HTTPS CRM URL")
        if "?" in self.base_url or "#" in self.base_url:
            raise ValueError("Fleet agent URL must not include query or fragment")
        if len(self.ingest_secret) < 24:
            raise ValueError("Fleet agent ingest secret must be at least 24 characters")
        if not 30 <= self.interval_seconds <= 3600:
            raise ValueError("Fleet heartbeat interval must be 30..3600 seconds")


def signed_heartbeat(config: FleetAgentConfig) -> tuple[bytes, dict[str, str]]:
    payload = {
        "event_id": "fleet-" + uuid.uuid4().hex,
        "type": "bot.heartbeat",
        "data": {"runtime_version": config.runtime_version},
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    stamp = str(int(time.time()))
    signature = hmac.new(
        config.ingest_secret.encode("utf-8"),
        stamp.encode("ascii") + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    return raw, {
        "X-Bot-Key": config.bot_key,
        "X-Timestamp": stamp,
        "X-Signature": signature,
        "Content-Type": "application/json",
    }


class FleetHeartbeatAgent:
    def __init__(
        self,
        config: FleetAgentConfig,
        *,
        sender: Callable[[str, bytes, dict[str, str]], Awaitable[None]] | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self._sender = sender or self._send_http
        self._task: asyncio.Task[None] | None = None

    @staticmethod
    async def _send_http(url: str, raw: bytes, headers: dict[str, str]) -> None:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.post(url, content=raw, headers=headers)
            response.raise_for_status()

    async def check_once(self) -> bool:
        if not self.config.enabled:
            return False
        raw, headers = signed_heartbeat(self.config)
        try:
            await self._sender(self.config.base_url.rstrip("/") + "/api/v1/events", raw, headers)
        except (httpx.HTTPError, OSError, TimeoutError):
            logger.warning("OmniFactory fleet heartbeat unavailable; will retry")
            return False
        return True

    async def _loop(self) -> None:
        while True:
            try:
                await self.check_once()
            except Exception:
                logger.exception("Unexpected OmniFactory heartbeat error")
            await asyncio.sleep(self.config.interval_seconds)

    async def start(self) -> None:
        if self.config.enabled and self._task is None:
            self._task = asyncio.create_task(self._loop(), name="omnifactory-fleet-heartbeat")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
