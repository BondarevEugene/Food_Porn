"""
==========================================================
FOOD_PORN

Module: Database Session Management
Layer: Persistence

Responsibilities:
    - Create the asynchronous SQLAlchemy engine
    - Provide transaction-scoped database sessions
    - Dispose database resources during shutdown
==========================================================
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def close(self) -> None:
        await self.engine.dispose()
