"""
==========================================================
FOOD_PORN & OLD MONEY MANIFESTATIONS
Module: Image Caching & Cost Optimization Service
==========================================================
"""

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ImageCache  # Або аналогічна модель у базі даних


class ImageCacheService:
    @staticmethod
    def compute_hash(goals: list[str], user_id: int) -> str:
        """Створює унікальний MD5-хеш на основі цілей та ID користувача."""
        raw_string = f"{user_id}:" + "_".join(sorted([g.strip().lower() for g in goals]))
        return hashlib.md5(raw_string.encode("utf-8")).hexdigest()

    @staticmethod
    async def get_cached_image(session: AsyncSession, cache_key: str) -> str | None:
        """Перевіряє, чи є вже готовий результат у кеші."""
        query = select(ImageCache).where(ImageCache.cache_key == cache_key)
        result = await session.execute(query)
        cached_record = result.scalars().first()

        if cached_record and Path(cached_record.file_path).exists():
            return cached_record.file_path
        return None

    @staticmethod
    async def save_to_cache(session: AsyncSession, cache_key: str, file_path: str) -> None:
        """Зберігає інформацію про кешоване зображення."""
        record = ImageCache(cache_key=cache_key, file_path=file_path)
        session.add(record)
        await session.commit()