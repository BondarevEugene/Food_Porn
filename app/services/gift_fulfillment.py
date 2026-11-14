"""Resumeable paid gift creation: collage assets, then optional MP4.

Only a purchase with a verified payment receipt may enter this pipeline.
A video-only purchase keeps the internal collage locked to customers.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aiogram import Bot
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.crm.models import GiftFulfillment, GiftPaymentReceipt, GiftPurchase
from app.database.models import VideoStoryOrder
from app.database.repositories import WallpaperOrderRepository
from app.services.gift_delivery import deliver_paid_gift
from app.services.goal_story import GoalScenePlanner
from app.services.replicate_vision_board import ReplicateVisionBoardRenderer
from app.services.video_story_render import render_verified_video_story
from app.services.wallpaper_studio import archive_source_photos

logger = logging.getLogger(__name__)
LEASE = timedelta(minutes=45)


class GiftFulfillmentBusy(RuntimeError):
    """Another worker already owns a live render lease."""


async def process_paid_gift_purchase(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    purchase_id: str,
    *, bot: Bot | None = None,
) -> GiftFulfillment:
    """Render only verified deliverables and persist all recovery checkpoints.

    This service never creates a payment, never modifies a quoted price, and
    never grants collage access for a video-only purchase.
    """
    async with factory() as session:
        purchase = await session.get(GiftPurchase, purchase_id, with_for_update=True)
        receipt = await session.get(GiftPaymentReceipt, purchase_id)
        if (
            purchase is None or receipt is None or purchase.status != "paid"
            or receipt.amount != purchase.total_amount
            or receipt.currency != purchase.currency
        ):
            raise ValueError("Verified paid gift purchase required")
        checkpoint = await session.get(GiftFulfillment, purchase_id, with_for_update=True)
        if checkpoint is None:
            checkpoint = GiftFulfillment(purchase_id=purchase_id)
            session.add(checkpoint)
            await session.flush()
        if checkpoint.status in {"ready", "delivering", "delivered"}:
            return checkpoint
        if checkpoint.status == "processing" and checkpoint.updated_at:
            timestamp = checkpoint.updated_at
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            if datetime.now(UTC) - timestamp < LEASE:
                raise GiftFulfillmentBusy("Paid gift render already running")
        checkpoint.status = "processing"
        checkpoint.updated_at = datetime.now(UTC)
        checkpoint.last_error = None
        wallpaper_order_id = checkpoint.wallpaper_order_id
        video_order_id = checkpoint.video_order_id
        owner_id = purchase.telegram_user_id
        await session.commit()

    try:
        if wallpaper_order_id is None:
            photos = [Path(value) for value in purchase.photo_paths]
            if not 1 <= len(photos) <= 7 or not all(path.is_file() for path in photos):
                raise FileNotFoundError("Original photos are missing; customer support is required")
            output_dir = (
                settings.generated_dir / "wallpapers" / str(owner_id)
                / f"gift_purchase_{purchase_id}"
            )
            planner = GoalScenePlanner(settings)
            planner.set_tracking_context(user_id=owner_id, order_id=purchase_id)
            plan = await planner.plan(photos=photos, goals=purchase.goals, lang="uk")
            archived_sources = await asyncio.to_thread(
                archive_source_photos, photos, output_dir
            )
            renderer = ReplicateVisionBoardRenderer(
                output_dir=output_dir, model=settings.wallpaper_image_model,
                quality=settings.wallpaper_image_quality,
            )
            renderer.set_tracking_context(user_id=owner_id, order_id=purchase_id)
            formats = await renderer.generate_goal_story(
                user_id=owner_id, photo_paths=photos, goals=purchase.goals,
                assignments=plan.assignments, scenes=plan.scenes,
                style=purchase.visual_style,
            )
            mobile, desktop = Path(formats["mobile"]), Path(formats["desktop"])
            for path in (mobile, desktop):
                if not path.is_file() or path.stat().st_size < 20_000:
                    raise RuntimeError("Generated artwork is incomplete")
                with Image.open(path) as image:
                    image.verify()
            async with factory() as session:
                # Internal artwork is an input to video, but does not grant
                # a customer the collage if only video was purchased.
                order = await WallpaperOrderRepository(session).create(
                    telegram_user_id=owner_id,
                    amount=purchase.collage_amount if purchase.includes_collage else 0,
                    mobile_path=str(mobile), desktop_path=str(desktop),
                    stars_amount=0, goals=list(purchase.goals),
                    scene_prompts=list(plan.scenes),
                    scene_assignments=list(plan.assignments),
                    source_photo_paths=archived_sources,
                    visual_style=purchase.visual_style,
                    raw_mobile_path=str(formats.get("raw_mobile", mobile)),
                    raw_desktop_path=str(formats.get("raw_desktop", desktop)),
                )
                wallpaper_order_id = order.id
                if purchase.includes_collage:
                    await WallpaperOrderRepository(session).mark_paid(
                        order, purchase_id, "gift_purchase"
                    )
                checkpoint = await session.get(GiftFulfillment, purchase_id)
                checkpoint.wallpaper_order_id = wallpaper_order_id
                checkpoint.updated_at = datetime.now(UTC)
                await session.commit()

        if purchase.includes_collage and purchase.includes_video and bot is not None:
            try:
                await deliver_paid_gift(factory, bot, purchase_id, partial=True)
            except Exception:
                # Rendering must continue even if Telegram delivery is temporarily down.
                logger.exception("Early collage delivery failed for %s", purchase_id)

        if purchase.includes_video:
            if video_order_id is not None:
                # Retry an incomplete MP4 without generating images twice.
                async with factory() as session:
                    previous = await session.get(
                        VideoStoryOrder, video_order_id, with_for_update=True
                    )
                    if previous is not None and previous.status == "failed":
                        previous.status = "paid"
                        previous.failure_reason = None
                        await session.commit()
            if video_order_id is None:
                async with factory() as session:
                    video = VideoStoryOrder(
                        wallpaper_order_id=wallpaper_order_id,
                        telegram_user_id=owner_id,
                        amount=0,
                        currency="UAH",
                        status="paid",
                        paid_at=datetime.now(UTC),
                        payment_reference=f"gift_purchase:{purchase_id}",
                        payment_system="gift_purchase",
                    )
                    session.add(video)
                    await session.flush()
                    video_order_id = video.id
                    checkpoint = await session.get(GiftFulfillment, purchase_id)
                    checkpoint.video_order_id = video_order_id
                    checkpoint.updated_at = datetime.now(UTC)
                    await session.commit()
            await render_verified_video_story(
                factory, settings, video_order_id, owner_id
            )

        async with factory() as session:
            checkpoint = await session.get(GiftFulfillment, purchase_id, with_for_update=True)
            checkpoint.status = "ready"
            checkpoint.last_error = None
            checkpoint.updated_at = datetime.now(UTC)
            await session.commit()
            return checkpoint
    except Exception as exc:
        logger.exception("Paid gift fulfillment failed for purchase %s", purchase_id)
        async with factory() as session:
            checkpoint = await session.get(GiftFulfillment, purchase_id, with_for_update=True)
            if checkpoint is not None:
                checkpoint.status = "failed"
                checkpoint.last_error = f"{type(exc).__name__}: {str(exc)[:400]}"
                checkpoint.updated_at = datetime.now(UTC)
                await session.commit()
        raise
