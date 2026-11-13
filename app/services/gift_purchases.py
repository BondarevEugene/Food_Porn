"""Create an immutable non-payable quote for the chosen wish product.

A quote never grants access and cannot trigger a payment. An integration must
later link it to a verified payment and a delivery entitlement.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.crm.models import GiftPurchase

CHOICES = frozenset({"collage", "video", "both"})


def quote_amounts(
    choice: str, *, collage_price: Decimal, video_price: Decimal | None
) -> tuple[Decimal, Decimal, Decimal]:
    if choice not in CHOICES:
        raise ValueError("Unsupported gift product")
    if collage_price <= 0 or not collage_price.is_finite():
        raise ValueError("Collage price must be positive")
    if choice in {"video", "both"} and (
        video_price is None or video_price <= 0 or not video_price.is_finite()
    ):
        raise ValueError("Video price must be configured before quoting")
    amounts = (
        collage_price if choice in {"collage", "both"} else Decimal("0"),
        video_price if choice in {"video", "both"} else Decimal("0"),
    )
    if any(value.as_tuple().exponent < -2 for value in amounts):
        raise ValueError("Prices cannot use fractional kopecks")
    return (*amounts, sum(amounts, Decimal("0")))


def quote_key(
    user_id: int,
    *,
    choice: str,
    goals: list[str],
    photos: list[str],
    style: str,
    collage_amount: Decimal,
    video_amount: Decimal,
) -> str:
    snapshot = {
        "owner": user_id,
        "choice": choice,
        "goals": goals,
        "photos": photos,
        "style": style,
        "collage_uah": str(collage_amount),
        "video_uah": str(video_amount),
    }
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


async def create_gift_quote(
    factory: async_sessionmaker[AsyncSession],
    *,
    settings: Settings,
    user_id: int,
    choice: str,
    goals: list[str],
    photo_paths: list[str | Path],
    style: str,
) -> GiftPurchase:
    if user_id < 1 or style not in {"dark", "light", "color"}:
        raise ValueError("Invalid owner or visual style")
    if not 5 <= len(goals) <= 9 or any(not value.strip() for value in goals):
        raise ValueError("The gift requires 5 to 9 nonempty goals")
    paths = [str(path) for path in photo_paths]
    if not 1 <= len(paths) <= 7 or any(not Path(path).is_absolute() for path in paths):
        raise ValueError("The gift requires 1 to 7 absolute source photo paths")
    collage, video, total = quote_amounts(
        choice,
        collage_price=settings.wayforpay_wallpaper_price_uah,
        video_price=settings.wayforpay_video_story_price_uah,
    )
    request_key = quote_key(
        user_id, choice=choice, goals=goals, photos=paths,
        style=style, collage_amount=collage, video_amount=video,
    )
    async with factory() as session:
        existing = await session.scalar(
            select(GiftPurchase).where(GiftPurchase.request_key == request_key)
        )
        if existing is not None:
            return existing
        purchase = GiftPurchase(
            request_key=request_key, telegram_user_id=user_id,
            product_choice=choice,
            includes_collage=choice in {"collage", "both"},
            includes_video=choice in {"video", "both"},
            currency="UAH", collage_amount=collage, video_amount=video,
            total_amount=total, goals=list(goals),
            photo_paths=paths, visual_style=style, status="quoted",
        )
        session.add(purchase)
        try:
            await session.commit()
        except IntegrityError:
            # Two concurrent requests with the same key produce a single quote.
            await session.rollback()
            existing = await session.scalar(
                select(GiftPurchase).where(GiftPurchase.request_key == request_key)
            )
            if existing is None:
                raise
            return existing
        await session.refresh(purchase)
        return purchase
