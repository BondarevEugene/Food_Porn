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

import hashlib
from io import BytesIO
from pathlib import Path

from aiogram import Bot
from PIL import Image, UnidentifiedImageError

from app.config import Settings


class InvalidImageError(ValueError):
    pass


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
        telegram_file = await bot.get_file(file_id)
        if telegram_file.file_size and telegram_file.file_size > self.settings.max_upload_mb * 1024**2:
            raise InvalidImageError("Image exceeds configured size limit")

        buffer = BytesIO()
        await bot.download(telegram_file, destination=buffer)
        payload = buffer.getvalue()
        if len(payload) > self.settings.max_upload_mb * 1024**2:
            raise InvalidImageError("Image exceeds configured size limit")
        return self.save_validated_bytes(payload, menu_id=menu_id, role=role)

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
