"""PostgreSQL-backed processing lease shared across application instances.

Lease renewal uses short independent transactions, suitable for a pooled Neon
connection. A lost lease cancels the processing task to avoid continued billing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import Menu, MenuStatus

logger = logging.getLogger(__name__)
LEASE_SECONDS = 300
HEARTBEAT_SECONDS = 30


class MenuProcessingLease:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], menu_id: int):
        self.session_factory = session_factory
        self.menu_id = menu_id
        self.token = uuid4().hex
        self._heartbeat_task: asyncio.Task | None = None
        self._owner_task: asyncio.Task | None = None

    async def acquire(self) -> bool:
        async with self.session_factory() as session:
            stmt = (
                update(Menu)
                .where(
                    Menu.id == self.menu_id,
                    Menu.status.notin_([MenuStatus.COMPLETED, MenuStatus.WAITING_FOR_PAYMENT]),
                    or_(
                        Menu.processing_lease_until.is_(None),
                        Menu.processing_lease_until < func.now(),
                    ),
                )
                .values(
                    processing_token=self.token,
                    processing_lease_until=func.now() + timedelta(seconds=LEASE_SECONDS),
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount == 1

    async def assert_owned(self) -> None:
        """Fail closed when another worker has acquired this menu."""
        async with self.session_factory() as session:
            owned = await session.scalar(
                select(Menu.id).where(
                    Menu.id == self.menu_id,
                    Menu.processing_token == self.token,
                    Menu.processing_lease_until > func.now(),
                )
            )
        if owned is None:
            raise RuntimeError(f"Processing lease lost for menu {self.menu_id}")

    async def renew(self) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(
                update(Menu)
                .where(Menu.id == self.menu_id, Menu.processing_token == self.token,
                       Menu.processing_lease_until > func.now())
                .values(processing_lease_until=func.now() + timedelta(seconds=LEASE_SECONDS))
            )
            await session.commit()
            return result.rowcount == 1

    async def release(self) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(Menu)
                .where(Menu.id == self.menu_id, Menu.processing_token == self.token)
                .values(processing_token=None, processing_lease_until=None)
            )
            await session.commit()

    async def _heartbeat(self) -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                if not await self.renew():
                    raise RuntimeError(f"Lost processing lease for menu {self.menu_id}")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Menu %s lease heartbeat failed; cancelling processing", self.menu_id)
            if self._owner_task is not None:
                self._owner_task.cancel()

    async def __aenter__(self) -> bool:
        acquired = await self.acquire()
        if acquired:
            self._owner_task = asyncio.current_task()
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
        return acquired

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            await asyncio.gather(self._heartbeat_task, return_exceptions=True)
        if self._owner_task is not None:
            self._owner_task = None
            await asyncio.shield(self.release())
