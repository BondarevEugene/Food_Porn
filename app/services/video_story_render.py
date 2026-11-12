"""Verified, single-claim MP4 render shared by Telegram and Scene Studio.

Only a separately paid video-story order may enter rendering. Rendering uses
saved collage assets without additional image-generation API calls.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.models import VideoStoryOrder, WallpaperOrder
from app.services.wallpaper_studio import WallpaperExportService


class VideoStoryNotPayable(ValueError):
    """The requested story is not an authorized paid order."""


class VideoStoryAlreadyProcessing(RuntimeError):
    """A worker already claimed this order."""


async def render_verified_video_story(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    video_order_id: int,
    owner_id: int,
    *,
    duration_seconds: int = 15,
    final_phrase: str = "",
) -> Path:
    if not 10 <= duration_seconds <= 20:
        raise ValueError("Video duration must be between 10 and 20 seconds")
    async with session_factory() as session:
        video = await session.get(VideoStoryOrder, video_order_id, with_for_update=True)
        if video is None or video.telegram_user_id != owner_id:
            raise VideoStoryNotPayable("Video story order not found")
        wallpaper = await session.get(WallpaperOrder, video.wallpaper_order_id)
        if wallpaper is None or wallpaper.telegram_user_id != owner_id or not wallpaper.paid:
            raise VideoStoryNotPayable("Paid parent artwork is required")
        if video.paid_at is None or video.status not in {"paid", "queued", "processing", "ready"}:
            raise VideoStoryNotPayable("A verified video payment is required")
        if video.status == "ready":
            stored = Path(video.output_path) if video.output_path else None
            if stored and stored.is_file():
                return stored
            raise FileNotFoundError("Ready video file is missing")
        if video.status == "processing":
            raise VideoStoryAlreadyProcessing("Video story already processing")
        # Claim the database row before spending CPU resources. A second worker
        # sees processing and cannot render the same paid order twice.
        video.status = "processing"
        await session.commit()
        parent = wallpaper
    try:
        service = WallpaperExportService(parent)
        phrase = " ".join(final_phrase.split()).strip()[:500] or "Твоя прекрасная история уже начинается."
        rendered = await service.render_video(
            settings=settings,
            goals=list(parent.goals or []),
            final_phrase=phrase,
            duration_seconds=duration_seconds,
            voice_path=None,
            music_path=None,
            ai_voice=False,
        )
        destination = Path(parent.mobile_path).parent / "scene_studio" / "video_orders"
        destination.mkdir(parents=True, exist_ok=True)
        output = destination / f"video_story_{video_order_id}.mp4"
        if Path(rendered).resolve() != output.resolve():
            await asyncio.to_thread(shutil.copyfile, rendered, output)
        async with session_factory() as session:
            current = await session.get(VideoStoryOrder, video_order_id, with_for_update=True)
            if current is None or current.status != "processing":
                raise RuntimeError("Video order processing state changed")
            current.output_path = str(output)
            current.status = "ready"
            current.failure_reason = None
            await session.commit()
        return output
    except Exception:
        async with session_factory() as session:
            current = await session.get(VideoStoryOrder, video_order_id, with_for_update=True)
            if current and current.status == "processing":
                current.status = "failed"
                current.failure_reason = "Video rendering failed; support intervention required"
                await session.commit()
        raise
