"""Durable, non-payable draft of the Telegram gift journey.

The draft is never used as proof of payment. Missing source files mean the
customer must re-upload them; stored paths are never trusted as arbitrary input.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.crm.models import GiftDraft

VALID_CHOICES = frozenset({"collage", "video", "both"})
VALID_STAGES = frozenset({"photos", "product", "goals", "ready"})


async def store_gift_draft(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    product_choice: str | None,
    goals: list[str] | None,
    photo_paths: list[str | Path],
    style: str,
    language: str,
    stage: str,
) -> None:
    if user_id <= 0 or product_choice not in (*VALID_CHOICES, None):
        raise ValueError("Invalid gift draft identity or product")
    if stage not in VALID_STAGES or style not in {"dark", "light", "color"}:
        raise ValueError("Invalid gift draft stage or style")
    paths = [str(path) for path in photo_paths]
    if len(paths) > 7 or any(not Path(path).is_absolute() for path in paths):
        raise ValueError("Gift draft photo paths must be absolute")
    async with session_factory() as session:
        row = await session.get(GiftDraft, user_id)
        if row is None:
            row = GiftDraft(telegram_user_id=user_id)
            session.add(row)
        row.product_choice = product_choice
        row.goals = list(goals or [])
        row.photo_paths = paths
        row.style = style
        row.language = language if language in {"uk", "ru", "en"} else "uk"
        row.stage = stage
        await session.commit()


async def load_gift_draft(
    session_factory: async_sessionmaker[AsyncSession], user_id: int
) -> GiftDraft | None:
    async with session_factory() as session:
        row = await session.get(GiftDraft, user_id)
        if row is None:
            return None
        # Return plain value object detached from SQLAlchemy session.
        return GiftDraft(
            telegram_user_id=row.telegram_user_id,
            product_choice=row.product_choice,
            goals=list(row.goals or []),
            photo_paths=list(row.photo_paths or []),
            style=row.style,
            language=row.language,
            stage=row.stage,
        )
