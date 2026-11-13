"""Deliver the selected gift products once after signed payment verification."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaDocument
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.crm.models import GiftFulfillment, GiftPaymentReceipt, GiftPurchase
from app.database.models import VideoStoryOrder, WallpaperOrder

logger = logging.getLogger(__name__)


async def deliver_paid_gift(
    factory: async_sessionmaker[AsyncSession], bot: Bot, purchase_id: str
) -> bool:
    """True if newly delivered; False if delivery was already completed.

    Each delivered product is checkpointed independently; failed deliveries
    are retryable without repeating a completed product.
    """
    async with factory() as session:
        purchase = await session.get(GiftPurchase, purchase_id)
        receipt = await session.get(GiftPaymentReceipt, purchase_id)
        job = await session.get(GiftFulfillment, purchase_id, with_for_update=True)
        if not purchase or not receipt or not job or purchase.status != "paid":
            raise ValueError("Verified gift purchase and fulfillment required")
        if job.status == "delivered":
            return False
        if job.status == "delivering":
            updated = job.updated_at
            if updated is not None:
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=UTC)
                if datetime.now(UTC) - updated < timedelta(minutes=20):
                    return False
        elif job.status != "ready":
            raise ValueError("Gift files are not yet ready")
        job.status = "delivering"
        job.updated_at = datetime.now(UTC)
        collage_sent, video_sent = job.collage_sent, job.video_sent
        wallpaper_id, video_id = job.wallpaper_order_id, job.video_order_id
        await session.commit()

    try:
        if purchase.includes_collage and not collage_sent:
            async with factory() as session:
                collage = await session.get(WallpaperOrder, wallpaper_id)
                if not collage or not collage.paid or collage.telegram_user_id != purchase.telegram_user_id:
                    raise ValueError("Paid collage entitlement missing")
                mobile, desktop = Path(collage.mobile_path), Path(collage.desktop_path)
            if not mobile.is_file() or not desktop.is_file():
                raise FileNotFoundError("Paid collage files missing")
            await bot.send_media_group(
                chat_id=purchase.telegram_user_id,
                media=[
                    InputMediaDocument(
                        media=FSInputFile(str(mobile)),
                        caption="💛 Ваш колаж готовий · телефон",
                    ),
                    InputMediaDocument(
                        media=FSInputFile(str(desktop)),
                        caption="🖼️ Версія для комп’ютера",
                    ),
                ],
            )
            async with factory() as session:
                job = await session.get(GiftFulfillment, purchase_id, with_for_update=True)
                job.collage_sent = True
                job.updated_at = datetime.now(UTC)
                await session.commit()

        if purchase.includes_video and not video_sent:
            async with factory() as session:
                video = await session.get(VideoStoryOrder, video_id)
                if (
                    video is None or video.telegram_user_id != purchase.telegram_user_id
                    or video.paid_at is None or video.status != "ready"
                    or not video.output_path
                ):
                    raise ValueError("Verified finished MP4 missing")
                output = Path(video.output_path)
            if not output.is_file():
                raise FileNotFoundError("MP4 is no longer stored")
            await bot.send_video(
                chat_id=purchase.telegram_user_id,
                video=FSInputFile(str(output)),
                caption="🎬 Ваша відеоісторія готова 💛",
            )
            async with factory() as session:
                job = await session.get(GiftFulfillment, purchase_id, with_for_update=True)
                job.video_sent = True
                job.updated_at = datetime.now(UTC)
                await session.commit()

        async with factory() as session:
            job = await session.get(GiftFulfillment, purchase_id, with_for_update=True)
            job.status = "delivered"
            job.updated_at = datetime.now(UTC)
            job.last_error = None
            await session.commit()
        return True
    except Exception as exc:
        logger.exception("Could not deliver paid gift %s", purchase_id)
        async with factory() as session:
            job = await session.get(GiftFulfillment, purchase_id, with_for_update=True)
            if job and job.status == "delivering":
                job.status = "ready"
                job.last_error = f"{type(exc).__name__}: {str(exc)[:400]}"
                job.updated_at = datetime.now(UTC)
                await session.commit()
        raise
