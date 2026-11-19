"""Durable, immutable release manifest for private Little Legend PDFs.

Neon stores only hashes, metadata and delivery status, never children's PDFs.
A single story cannot silently replace an already sealed release.
"""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.session import async_session_maker
from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.release_package import ReleasePackage

metadata = MetaData()
release_manifests = Table(
    "little_legend_release_manifests", metadata,
    Column(
        "story_id", Integer,
        ForeignKey("little_legend_stories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("owner_id", BigInteger, nullable=False, index=True),
    Column("revision_fingerprint", String(64), nullable=False),
    Column("pdf_sha256", String(64), nullable=False),
    Column("scene_count", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("telegram_message_id", BigInteger, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class ReleaseManifest(BaseModel):
    owner_id: int = Field(gt=0)
    story_id: int = Field(gt=0)
    revision_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scene_count: int = Field(ge=1, le=40)
    status: DeliveryStatus
    telegram_message_id: int | None = Field(default=None, gt=0)
    created_at: datetime
    updated_at: datetime


def _decode(row) -> ReleaseManifest:
    return ReleaseManifest.model_validate(dict(row))


async def register_release(
    *, package: ReleasePackage, owner_id: int, story_id: int,
) -> ReleaseManifest:
    """Register only after a verified private PDF object has been stored.

    The caller must persist the object first; registering does not upload it.
    """
    package.verified_pdf(owner_id=owner_id, story_id=story_id)
    release = package.release
    if package.delivery.status != DeliveryStatus.READY:
        raise PermissionError("Only an undispatched release can be registered")
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        from app.little_legend.router import stories

        exists = (await session.execute(select(stories.c.id).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ).with_for_update())).scalar_one_or_none()
        if exists is None:
            raise PermissionError("Story not found")
        await session.execute(pg_insert(release_manifests).values(
            story_id=story_id, owner_id=owner_id,
            revision_fingerprint=release.revision_fingerprint,
            pdf_sha256=release.pdf_sha256,
            scene_count=release.scene_count,
            status=DeliveryStatus.READY.value,
            created_at=now, updated_at=now,
        ).on_conflict_do_nothing(index_elements=["story_id"]))
        row = (await session.execute(select(release_manifests).where(
            release_manifests.c.story_id == story_id,
            release_manifests.c.owner_id == owner_id,
        ))).mappings().one_or_none()
        if row is None or (
            row["revision_fingerprint"] != release.revision_fingerprint
            or row["pdf_sha256"] != release.pdf_sha256
            or row["scene_count"] != release.scene_count
        ):
            raise PermissionError("Story already has a different sealed release")
        await session.commit()
        return _decode(row)


async def get_release_manifest(
    *, owner_id: int, story_id: int,
) -> ReleaseManifest | None:
    async with async_session_maker() as session:
        row = (await session.execute(select(release_manifests).where(
            release_manifests.c.story_id == story_id,
            release_manifests.c.owner_id == owner_id,
        ))).mappings().one_or_none()
        return _decode(row) if row else None


async def mark_release_delivery(
    *, owner_id: int, story_id: int, pdf_sha256: str,
    status: DeliveryStatus, message_id: int | None = None,
) -> ReleaseManifest:
    """Mirror committed Telegram effect status without allowing a resend.

    This is a status projection; the effect ledger is the dispatch authority.
    """
    if status not in {DeliveryStatus.SENT, DeliveryStatus.UNCERTAIN}:
        raise ValueError("Only terminal dispatch outcomes can be recorded")
    if status == DeliveryStatus.SENT and (
        not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0
    ):
        raise ValueError("Confirmed Telegram message ID required")
    if status == DeliveryStatus.UNCERTAIN and message_id is not None:
        raise ValueError("Uncertain delivery cannot have a message ID")
    async with async_session_maker() as session:
        row = (await session.execute(select(release_manifests).where(
            release_manifests.c.story_id == story_id,
            release_manifests.c.owner_id == owner_id,
            release_manifests.c.pdf_sha256 == pdf_sha256,
        ).with_for_update())).mappings().one_or_none()
        if row is None:
            raise PermissionError("Sealed release not found")
        if row["status"] == DeliveryStatus.SENT.value:
            if status != DeliveryStatus.SENT or row["telegram_message_id"] != message_id:
                raise PermissionError("Confirmed delivery is immutable")
            return _decode(row)
        if row["status"] == DeliveryStatus.UNCERTAIN.value and status != DeliveryStatus.SENT:
            return _decode(row)
        await session.execute(update(release_manifests).where(
            release_manifests.c.story_id == story_id,
            release_manifests.c.owner_id == owner_id,
        ).values(
            status=status.value, telegram_message_id=message_id,
            updated_at=datetime.now(UTC),
        ))
        await session.commit()
    manifest = await get_release_manifest(owner_id=owner_id, story_id=story_id)
    if manifest is None:
        raise PermissionError("Release disappeared")
    return manifest
