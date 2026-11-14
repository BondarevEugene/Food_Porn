"""The paid gift worker creates only purchased deliverables."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.crm.models import CRMBase, GiftFulfillment, GiftPaymentReceipt
from app.database.models import Base, VideoStoryOrder, WallpaperOrder
from app.services import gift_delivery, gift_fulfillment
from app.services.gift_purchases import create_gift_quote


@pytest.fixture
async def fulfillment_factory(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "fulfill.db"))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(CRMBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None, storage_root=tmp_path,
        wayforpay_wallpaper_price_uah=Decimal("15.00"),
        wayforpay_video_story_price_uah=Decimal("49.00"),
    )
    photo = tmp_path / "portrait.jpg"
    Image.new("RGB", (320, 420), "#bb9988").save(photo)
    calls = {"plan": 0, "render": 0, "video": 0}

    class Planner:
        def __init__(self, settings):
            pass

        def set_tracking_context(self, **kwargs):
            pass

        async def plan(self, *, photos, goals, lang):
            calls["plan"] += 1
            return SimpleNamespace(
                assignments=tuple(0 for _ in goals),
                scenes=tuple("scene" for _ in goals),
            )

    class Renderer:
        def __init__(self, **kwargs):
            pass

        def set_tracking_context(self, **kwargs):
            pass

        async def generate_goal_story(self, **kwargs):
            calls["render"] += 1
            mobile = tmp_path / "mobile.png"
            desktop = tmp_path / "desktop.png"
            noise = Image.effect_noise((1024, 1024), 70).convert("RGB")
            noise.save(mobile)
            noise.save(desktop)
            return {"mobile": mobile, "desktop": desktop}

    async def video_render(factory, settings, order_id, owner_id):
        calls["video"] += 1
        async with factory() as session:
            video = await session.get(VideoStoryOrder, order_id)
            parent = await session.get(WallpaperOrder, video.wallpaper_order_id)
            assert video.paid_at is not None
            assert parent.telegram_user_id == owner_id
            output = tmp_path / "film.mp4"
            output.write_bytes(b"mock movie")
            video.status = "ready"
            video.output_path = str(output)
            await session.commit()
            return output

    monkeypatch.setattr(gift_fulfillment, "GoalScenePlanner", Planner)
    monkeypatch.setattr(gift_fulfillment, "ReplicateVisionBoardRenderer", Renderer)
    monkeypatch.setattr(
        gift_fulfillment, "archive_source_photos", lambda photos, root: [str(photo)]
    )
    monkeypatch.setattr(gift_fulfillment, "render_verified_video_story", video_render)
    yield factory, settings, photo, calls
    await engine.dispose()


async def _purchase(factory, settings, photo, choice):
    purchase = await create_gift_quote(
        factory, settings=settings, user_id=42, choice=choice,
        goals=[f"goal {index}" for index in range(5)],
        photo_paths=[photo], style="dark",
    )
    async with factory() as session:
        session.add(GiftPaymentReceipt(
            purchase_id=purchase.id, provider="wayforpay",
            provider_payment_id=f"verified-{choice}",
            amount=purchase.total_amount, currency="UAH",
        ))
        purchase.status = "paid"
        await session.merge(purchase)
        await session.commit()
    return purchase


@pytest.mark.asyncio
@pytest.mark.parametrize(("choice", "collage_paid", "video_calls"), [
    ("collage", True, 0),
    ("video", False, 1),
    ("both", True, 1),
])
async def test_paid_gift_fulfills_only_selected_outputs(
    fulfillment_factory, choice, collage_paid, video_calls
):
    factory, settings, photo, calls = fulfillment_factory
    purchase = await _purchase(factory, settings, photo, choice)
    checkpoint = await gift_fulfillment.process_paid_gift_purchase(
        factory, settings, purchase.id
    )
    assert checkpoint.status == "ready"
    assert checkpoint.wallpaper_order_id is not None
    assert calls["render"] == 1
    assert calls["video"] == video_calls
    async with factory() as session:
        wallpaper = await session.get(WallpaperOrder, checkpoint.wallpaper_order_id)
        assert wallpaper.paid is collage_paid
        if video_calls:
            video = await session.get(VideoStoryOrder, checkpoint.video_order_id)
            assert video.status == "ready"
        else:
            assert checkpoint.video_order_id is None
    again = await gift_fulfillment.process_paid_gift_purchase(
        factory, settings, purchase.id
    )
    assert again.wallpaper_order_id == checkpoint.wallpaper_order_id
    assert calls["render"] == 1
    assert calls["video"] == video_calls


@pytest.mark.asyncio
async def test_unpaid_purchase_cannot_render(fulfillment_factory):
    factory, settings, photo, calls = fulfillment_factory
    purchase = await create_gift_quote(
        factory, settings=settings, user_id=42, choice="both",
        goals=["goal"] * 5, photo_paths=[photo], style="dark",
    )
    with pytest.raises(ValueError, match="Verified paid"):
        await gift_fulfillment.process_paid_gift_purchase(
            factory, settings, purchase.id
        )
    assert calls["render"] == 0


@pytest.mark.asyncio
async def test_running_fulfillment_cannot_be_claimed_twice(fulfillment_factory):
    factory, settings, photo, calls = fulfillment_factory
    purchase = await _purchase(factory, settings, photo, "video")
    async with factory() as session:
        session.add(GiftFulfillment(
            purchase_id=purchase.id, status="processing",
            updated_at=datetime.now(UTC),
        ))
        await session.commit()
    with pytest.raises(gift_fulfillment.GiftFulfillmentBusy):
        await gift_fulfillment.process_paid_gift_purchase(
            factory, settings, purchase.id
        )
    assert calls["render"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(("choice", "send_collage", "send_video"), [
    ("collage", True, False),
    ("video", False, True),
    ("both", True, True),
])
async def test_delivery_sends_only_paid_products_once(
    fulfillment_factory, choice, send_collage, send_video
):
    factory, settings, photo, calls = fulfillment_factory
    purchase = await _purchase(factory, settings, photo, choice)
    await gift_fulfillment.process_paid_gift_purchase(
        factory, settings, purchase.id
    )
    bot = SimpleNamespace(send_media_group=AsyncMock(), send_video=AsyncMock())
    assert await gift_delivery.deliver_paid_gift(factory, bot, purchase.id)
    assert not await gift_delivery.deliver_paid_gift(factory, bot, purchase.id)
    assert bot.send_media_group.await_count == int(send_collage)
    assert bot.send_video.await_count == int(send_video)
    async with factory() as session:
        checkpoint = await session.get(GiftFulfillment, purchase.id)
        assert checkpoint.status == "delivered"
        assert checkpoint.collage_sent is send_collage
        assert checkpoint.video_sent is send_video


@pytest.mark.asyncio
async def test_failed_video_send_can_resume_without_resending_collage(
    fulfillment_factory
):
    factory, settings, photo, calls = fulfillment_factory
    purchase = await _purchase(factory, settings, photo, "both")
    await gift_fulfillment.process_paid_gift_purchase(
        factory, settings, purchase.id
    )
    bot = SimpleNamespace(
        send_media_group=AsyncMock(),
        send_video=AsyncMock(side_effect=RuntimeError("Temporary Telegram failure")),
    )
    with pytest.raises(RuntimeError, match="Temporary"):
        await gift_delivery.deliver_paid_gift(factory, bot, purchase.id)
    async with factory() as session:
        checkpoint = await session.get(GiftFulfillment, purchase.id)
        assert checkpoint.status == "ready"
        assert checkpoint.collage_sent is True
        assert checkpoint.video_sent is False
    bot.send_video = AsyncMock()
    assert await gift_delivery.deliver_paid_gift(factory, bot, purchase.id)
    bot.send_media_group.assert_awaited_once()
    bot.send_video.assert_awaited_once()


@pytest.mark.asyncio
async def test_bundle_delivers_collage_before_video_finishes(fulfillment_factory, monkeypatch):
    factory, settings, photo, calls = fulfillment_factory
    purchase = await _purchase(factory, settings, photo, "both")
    bot = SimpleNamespace(send_media_group=AsyncMock(), send_video=AsyncMock())
    async def render_after_collage(factory, settings, order_id, owner_id):
        assert bot.send_media_group.await_count == 1
        assert bot.send_video.await_count == 0
        async with factory() as session:
            checkpoint = await session.get(GiftFulfillment, purchase.id)
            assert checkpoint.collage_sent is True
            assert checkpoint.video_sent is False
            assert checkpoint.status == "processing"
            video = await session.get(VideoStoryOrder, order_id)
            output = settings.storage_root / "early-film.mp4"
            output.write_bytes(b"movie")
            video.output_path = str(output)
            video.status = "ready"
            await session.commit()
    monkeypatch.setattr(gift_fulfillment, "render_verified_video_story", render_after_collage)
    await gift_fulfillment.process_paid_gift_purchase(
        factory, settings, purchase.id, bot=bot
    )
    assert await gift_delivery.deliver_paid_gift(factory, bot, purchase.id)
    assert bot.send_media_group.await_count == 1
    assert bot.send_video.await_count == 1


@pytest.mark.asyncio
async def test_video_only_does_not_deliver_internal_artwork_early(fulfillment_factory):
    factory, settings, photo, calls = fulfillment_factory
    purchase = await _purchase(factory, settings, photo, "video")
    bot = SimpleNamespace(send_media_group=AsyncMock(), send_video=AsyncMock())
    await gift_fulfillment.process_paid_gift_purchase(factory, settings, purchase.id, bot=bot)
    bot.send_media_group.assert_not_awaited()
    assert await gift_delivery.deliver_paid_gift(factory, bot, purchase.id)
    bot.send_media_group.assert_not_awaited()
    bot.send_video.assert_awaited_once()


@pytest.mark.asyncio
async def test_early_collage_send_failure_does_not_block_video(fulfillment_factory):
    factory, settings, photo, calls = fulfillment_factory
    purchase = await _purchase(factory, settings, photo, "both")
    bot = SimpleNamespace(
        send_media_group=AsyncMock(side_effect=RuntimeError("Telegram unavailable")),
        send_video=AsyncMock(),
    )
    result = await gift_fulfillment.process_paid_gift_purchase(
        factory, settings, purchase.id, bot=bot
    )
    assert result.status == "ready"
    assert calls["video"] == 1
    bot.send_media_group = AsyncMock()
    assert await gift_delivery.deliver_paid_gift(factory, bot, purchase.id)
    bot.send_media_group.assert_awaited_once()
    bot.send_video.assert_awaited_once()
