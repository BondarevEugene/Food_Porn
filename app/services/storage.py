"""
==========================================================
FOOD_PORN

Module: Image Storage Service
Layer: Service

Responsibilities:
    - Download Telegram photo uploads safely
    - Validate image type, dimensions, and byte limits
    - Normalize accepted images for reliable rendering
==========================================================
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from io import BytesIO
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError
from PIL import Image, UnidentifiedImageError

from app.config import Settings

logger = logging.getLogger(__name__)


class InvalidImageError(ValueError):
    pass


class PhotoTransferUnavailable(RuntimeError):
    """Telegram API request timed out; a retry is needed."""


class StorageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def save_telegram_photo(
        self,
        bot: Bot,
        file_id: str,
        *,
        menu_id: int,
        role: str,
    ) -> Path:
        started = time.perf_counter()
        max_bytes = self.settings.max_upload_mb * 1024**2
        for attempt in range(2):
            try:
                telegram_file = await asyncio.wait_for(bot.get_file(file_id), timeout=12)
                if telegram_file.file_size and telegram_file.file_size > max_bytes:
                    raise InvalidImageError("Image exceeds configured size limit")
                buffer = BytesIO()
                await asyncio.wait_for(
                    bot.download(telegram_file, destination=buffer), timeout=25
                )
                payload = buffer.getvalue()
                if len(payload) > max_bytes:
                    raise InvalidImageError("Image exceeds configured size limit")
                path = await asyncio.to_thread(
                    self.save_validated_bytes, payload, menu_id=menu_id, role=role
                )
                logger.info(
                    "Menu photo ready: menu=%s role=%s bytes=%s elapsed=%.2fs attempts=%s",
                    menu_id, role, len(payload),
                    time.perf_counter() - started, attempt + 1,
                )
                return path
            except (TelegramNetworkError, TimeoutError) as exc:
                logger.warning(
                    "Telegram photo transfer failed (menu=%s role=%s attempt=%s): %s",
                    menu_id, role, attempt + 1, type(exc).__name__,
                )
                if attempt == 1:
                    raise PhotoTransferUnavailable(
                        "Telegram photo transfer timed out"
                    ) from exc
                await asyncio.sleep(1)
        raise PhotoTransferUnavailable("Telegram photo transfer unavailable")

    def save_validated_bytes(self, payload: bytes, *, menu_id: int, role: str) -> Path:
        try:
            with Image.open(BytesIO(payload)) as image:
                image.verify()
            with Image.open(BytesIO(payload)) as image:
                image = image.convert("RGB")
                image.thumbnail((5000, 5000), Image.Resampling.LANCZOS)
                digest = hashlib.sha256(payload).hexdigest()[:12]
                directory = self.settings.uploads_dir / str(menu_id)
                directory.mkdir(parents=True, exist_ok=True)
                path = directory / f"{role}_{digest}.jpg"
                image.save(path, "JPEG", quality=94, optimize=True)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise InvalidImageError("Unsupported or corrupt image") from exc
        return path
