"""Durable, owner-scoped Little Legend consent event journal.

The published photo policy is still a draft. This module intentionally does
NOT provide an operation that grants permission to upload child photographs.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.little_legend.consent import POLICY_VERSION
from app.little_legend.vault_operations import queue_story_deletion
from app.little_legend.vault_registry import stories_table


class ConsentEventType(StrEnum):
    TERMS_ACCEPTED = "terms_accepted"
    PHOTO_WITHDRAWN = "photo_withdrawn"


metadata = MetaData()
consent_events = Table(
    "little_legend_consent_events",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("owner_id", BigInteger, nullable=False),
    Column("story_id", Integer, ForeignKey("little_legend_stories.id"), nullable=False),
    Column("policy_version", String(80), nullable=False),
    Column("event_type", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "event_type IN ('terms_accepted', 'photo_withdrawn')",
        name="ck_ll_consent_event_type",
    ),
    Index(
        "ix_ll_consent_owner_story_created",
        "owner_id", "story_id", "created_at",
    ),
)


async def append_consent_event(
    session: AsyncSession, *, owner_id: int, story_id: int,
    event_type: ConsentEventType, now: datetime | None = None,
) -> None:
    """Write event only for an owned story, without recording sensitive media."""
    if owner_id <= 0 or story_id <= 0:
        raise ValueError("Invalid owner or story")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    result = await session.execute(
        insert(consent_events).from_select(
            ["owner_id", "story_id", "policy_version", "event_type", "created_at"],
            select(
                owner_id, story_id, POLICY_VERSION, event_type.value, instant
            ).where(
                select(1).select_from(stories_table).where(
                    stories_table.c.id == story_id,
                    stories_table.c.owner_id == owner_id,
                ).exists()
            ),
        )
    )
    if result.rowcount == 0:
        raise PermissionError("Story not found")


async def withdraw_and_queue_private_media(
    session: AsyncSession, *, owner_id: int, story_id: int,
) -> int:
    """Append withdrawal and queue erasure in caller-owned DB transaction.

    Caller must commit. Object deletion happens separately; no claim that
    bytes have been erased is made by this function.
    """
    await append_consent_event(
        session, owner_id=owner_id, story_id=story_id,
        event_type=ConsentEventType.PHOTO_WITHDRAWN,
    )
    return await queue_story_deletion(
        session, owner_id=owner_id, story_id=story_id
    )
