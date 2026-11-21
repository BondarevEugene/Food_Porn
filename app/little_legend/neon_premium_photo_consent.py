"""Owner-scoped Neon repository for the premium child-photo transfer consent."""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.session import async_session_maker
from app.little_legend.premium_photo_consent import PremiumPhotoConsent
from app.little_legend.vault_registry import stories_table

metadata = MetaData()
premium_photo_consents = Table(
    "little_legend_premium_photo_consents", metadata,
    Column("story_id", Integer, primary_key=True),
    Column("owner_id", BigInteger, nullable=False),
    Column("provider", String(200), nullable=False),
    Column("notice_snapshot", String(4000), nullable=False),
    Column("accepted_at", DateTime(timezone=True), nullable=False),
    Column("withdrawn_at", DateTime(timezone=True)),
)


class NeonPremiumPhotoConsentRepository:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.session_factory = session_factory or async_session_maker

    async def get_photo_consent(
        self, *, owner_id: int, story_id: int,
    ) -> PremiumPhotoConsent:
        if owner_id <= 0 or story_id <= 0:
            raise PermissionError("Story not found")
        async with self.session_factory() as session:
            row = (await session.execute(
                select(premium_photo_consents).where(
                    premium_photo_consents.c.owner_id == owner_id,
                    premium_photo_consents.c.story_id == story_id,
                )
            )).mappings().one_or_none()
        if row is None:
            return PremiumPhotoConsent()
        return PremiumPhotoConsent(
            active=row["withdrawn_at"] is None,
            provider=row["provider"],
            notice_snapshot=row["notice_snapshot"],
            accepted_at=row["accepted_at"],
            withdrawn_at=row["withdrawn_at"],
        )

    async def accept(
        self, *, owner_id: int, story_id: int, consent: PremiumPhotoConsent,
    ) -> None:
        if not consent.active or consent.accepted_at is None:
            raise PermissionError("Explicit parental consent required")
        if consent.withdrawn_at is not None:
            raise PermissionError("Withdrawn consent cannot be accepted")
        async with self.session_factory() as session:
            owned = (await session.execute(select(1).select_from(
                stories_table,
            ).where(
                stories_table.c.id == story_id,
                stories_table.c.owner_id == owner_id,
            ))).scalar_one_or_none()
            if owned is None:
                raise PermissionError("Story not found")
            existing = (await session.execute(
                select(premium_photo_consents.c.story_id).where(
                    premium_photo_consents.c.story_id == story_id,
                    premium_photo_consents.c.owner_id == owner_id,
                )
            )).scalar_one_or_none()
            values = {
                "provider": consent.provider,
                "notice_snapshot": consent.notice_snapshot,
                "accepted_at": consent.accepted_at,
                "withdrawn_at": None,
            }
            if existing is None:
                await session.execute(insert(premium_photo_consents).values(
                    owner_id=owner_id, story_id=story_id, **values,
                ))
            else:
                await session.execute(update(premium_photo_consents).where(
                    premium_photo_consents.c.story_id == story_id,
                    premium_photo_consents.c.owner_id == owner_id,
                ).values(**values))
            await session.commit()

    async def withdraw(self, *, owner_id: int, story_id: int) -> None:
        from datetime import UTC, datetime

        async with self.session_factory() as session:
            result = await session.execute(
                update(premium_photo_consents).where(
                    premium_photo_consents.c.owner_id == owner_id,
                    premium_photo_consents.c.story_id == story_id,
                    premium_photo_consents.c.withdrawn_at.is_(None),
                ).values(withdrawn_at=datetime.now(UTC))
            )
            if result.rowcount != 1:
                raise PermissionError("Active consent not found")
            await session.commit()
