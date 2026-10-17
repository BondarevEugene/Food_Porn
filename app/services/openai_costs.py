"""
==========================================================
FOOD_PORN

Module: OpenAI Organization Cost Synchronizer
Layer: Service

Responsibilities:
    - Import actual billed OpenAI cost buckets with an organization Admin key
    - Store idempotent provider ledger rows for CRM reconciliation
    - Run periodically without delaying application startup
==========================================================
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.models import ProviderCost

logger = logging.getLogger(__name__)


def _utc_timestamp(value: Any) -> datetime:
    return datetime.fromtimestamp(int(value), tz=UTC)


def _external_key(bucket: dict[str, Any], item: dict[str, Any]) -> str:
    stable = {
        "start_time": bucket.get("start_time"),
        "end_time": bucket.get("end_time"),
        "amount": item.get("amount"),
        "line_item": item.get("line_item"),
        "project_id": item.get("project_id"),
        "organization_id": item.get("organization_id"),
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()


class OpenAICostSynchronizer:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.last_error: str | None = None
        self.last_synced_at: datetime | None = None

    @property
    def configured(self) -> bool:
        secret = getattr(self.settings, "openai_admin_api_key", None)
        key = secret.get_secret_value() if secret is not None else ""
        return bool(key and key != "replace_me")

    async def start(self) -> None:
        if not getattr(self.settings, "openai_cost_sync_enabled", False) or not self.configured or self._task:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="openai-cost-sync")

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop.set()
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.sync_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("OpenAI cost synchronization failed")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=getattr(self.settings, "openai_cost_sync_interval_minutes", 60) * 60,
                )
            except TimeoutError:
                pass

    async def sync_once(self, *, days: int | None = None) -> int:
        if not self.configured:
            raise RuntimeError("OPENAI_ADMIN_API_KEY is not configured")
        end = datetime.now(UTC)
        begin = end - timedelta(days=days or getattr(self.settings, "openai_cost_sync_days", 35))
        buckets = await self._fetch(begin, end)
        imported = 0
        async with self.session_factory() as session:
            for bucket in buckets:
                for item in bucket.get("results") or []:
                    imported += await self._store(session, bucket, item)
            await session.commit()
        self.last_error = None
        self.last_synced_at = datetime.now(UTC)
        logger.info("OpenAI cost synchronization complete: %s new rows", imported)
        return imported

    async def _fetch(self, begin: datetime, end: datetime) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "start_time": int(begin.timestamp()),
            "end_time": int(end.timestamp()),
            "bucket_width": "1d",
            "limit": 180,
            "group_by": ["project_id", "line_item"],
        }
        project_id = getattr(self.settings, "openai_project_id", "")
        if project_id:
            params["project_ids"] = [project_id]
        output: list[dict[str, Any]] = []
        page: str | None = None
        client = AsyncOpenAI(
            admin_api_key=self.settings.openai_admin_api_key.get_secret_value(),
            timeout=30,
            max_retries=2,
        )
        try:
            while True:
                if page:
                    params["page"] = page
                response = await client.admin.organization.usage.costs(**params)
                payload = response.model_dump()
                data = payload.get("data", [])
                if not isinstance(data, list):
                    raise RuntimeError("OpenAI costs response has no data list")
                output.extend(item for item in data if isinstance(item, dict))
                if not payload.get("has_more"):
                    break
                page = payload.get("next_page")
                if not page:
                    raise RuntimeError("OpenAI costs response has_more without next_page")
        finally:
            await client.close()
        return output

    async def _store(
        self, session: AsyncSession, bucket: dict[str, Any], item: dict[str, Any]
    ) -> int:
        amount = item.get("amount") or {}
        value = Decimal(str(amount.get("value", "0")))
        if value < 0:
            return 0
        key = _external_key(bucket, item)
        existing = await session.scalar(select(ProviderCost.id).where(ProviderCost.external_key == key))
        if existing:
            return 0
        session.add(
            ProviderCost(
                provider="openai",
                external_key=key,
                bucket_start=_utc_timestamp(bucket["start_time"]),
                bucket_end=_utc_timestamp(bucket["end_time"]),
                amount=value,
                currency=str(amount.get("currency") or "usd").lower(),
                project_id=item.get("project_id"),
                line_item=item.get("line_item"),
                details={"organization_id": item.get("organization_id")},
            )
        )
        return 1
