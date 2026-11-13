"""Money and idempotency contracts for non-payable gift quotes."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.crm.models import CRMBase, GiftPurchase
from app.services.gift_purchases import create_gift_quote, quote_amounts


@pytest.mark.parametrize(
    ("choice", "collage", "video", "total"),
    [
        ("collage", "15.00", "0", "15.00"),
        ("video", "0", "49.00", "49.00"),
        ("both", "15.00", "49.00", "64.00"),
    ],
)
def test_quote_has_exact_product_entitlements(choice, collage, video, total):
    values = quote_amounts(
        choice, collage_price=Decimal("15.00"), video_price=Decimal("49.00")
    )
    assert values == tuple(Decimal(amount) for amount in (collage, video, total))


def test_video_quote_is_disabled_without_admin_price():
    with pytest.raises(ValueError, match="Video price"):
        quote_amounts("video", collage_price=Decimal("15.00"), video_price=None)
    with pytest.raises(ValueError, match="Video price"):
        quote_amounts("both", collage_price=Decimal("15.00"), video_price=None)
    with pytest.raises(ValueError, match="Unsupported"):
        quote_amounts("unknown", collage_price=Decimal("15.00"), video_price=None)


@pytest.mark.asyncio
async def test_quote_persists_and_is_idempotent_across_sessions(tmp_path):
    db = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "quote.db"))
    async with db.begin() as conn:
        await conn.run_sync(CRMBase.metadata.create_all)
    factory = async_sessionmaker(db, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        wayforpay_wallpaper_price_uah=Decimal("15.00"),
        wayforpay_video_story_price_uah=Decimal("49.00"),
    )
    payload = dict(
        settings=settings, user_id=42, choice="both",
        goals=[f"wish {i}" for i in range(5)],
        photo_paths=[tmp_path / "portrait.jpg"], style="light",
    )
    first = await create_gift_quote(factory, **payload)
    second = await create_gift_quote(factory, **payload)
    assert first.id == second.id
    assert first.total_amount == Decimal("64.00")
    assert first.includes_collage and first.includes_video
    assert first.status == "quoted"
    # Editing one wish yields a new order without mutating an earlier price.
    third = await create_gift_quote(
        factory, **{**payload, "goals": ["changed", *payload["goals"][1:]]}
    )
    assert third.id != first.id
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(GiftPurchase)) == 2
    await db.dispose()


@pytest.mark.asyncio
async def test_quote_refuses_missing_or_invalid_input(tmp_path):
    db = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "invalid.db"))
    factory = async_sessionmaker(db, expire_on_commit=False)
    settings = Settings(_env_file=None)
    with pytest.raises(ValueError, match="5 to 9"):
        await create_gift_quote(
            factory, settings=settings, user_id=42, choice="collage",
            goals=["one"], photo_paths=[tmp_path / "a.jpg"], style="dark",
        )
    with pytest.raises(ValueError, match="absolute"):
        await create_gift_quote(
            factory, settings=settings, user_id=42, choice="collage",
            goals=["one"] * 5, photo_paths=["a.jpg"], style="dark",
        )
    await db.dispose()
