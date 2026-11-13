"""
==========================================================
FOOD_PORN

Module: Storage Service Tests
Layer: Test

Responsibilities:
    - Verify accepted images are normalized
    - Verify invalid image payloads are rejected
==========================================================
"""

import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.config import Settings
from app.services.storage import InvalidImageError, PhotoTransferUnavailable, StorageService


def test_valid_image_is_normalized(tmp_path) -> None:
    source = BytesIO()
    Image.new("RGBA", (100, 80), (200, 30, 20, 120)).save(source, "PNG")
    service = StorageService(Settings(storage_root=tmp_path))
    path = service.save_validated_bytes(source.getvalue(), menu_id=7, role="cover")
    assert path.exists()
    with Image.open(path) as saved:
        assert saved.mode == "RGB"
        assert saved.format == "JPEG"


def test_invalid_image_is_rejected(tmp_path) -> None:
    service = StorageService(Settings(storage_root=tmp_path))
    with pytest.raises(InvalidImageError):
        service.save_validated_bytes(b"not an image", menu_id=7, role="cover")


@pytest.mark.asyncio
async def test_telegram_photo_download_timeout_is_bounded_and_retriable(tmp_path, monkeypatch):
    service = StorageService(Settings(_env_file=None, storage_root=tmp_path))
    bot = SimpleNamespace(get_file=AsyncMock(side_effect=TimeoutError()), download=AsyncMock())

    async def no_sleep(delay):
        return None

    monkeypatch.setattr("app.services.storage.asyncio.sleep", no_sleep)
    with pytest.raises(PhotoTransferUnavailable, match="timed out"):
        await service.save_telegram_photo(bot, "file:1", menu_id=7, role="cover")
    assert bot.get_file.await_count == 2
    bot.download.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_photo_recovers_from_one_timeout(tmp_path, monkeypatch):
    service = StorageService(Settings(_env_file=None, storage_root=tmp_path))
    photo = BytesIO()
    Image.new("RGB", (240, 300), "white").save(photo, "JPEG")

    async def no_sleep(delay):
        return None

    monkeypatch.setattr("app.services.storage.asyncio.sleep", no_sleep)
    bot = SimpleNamespace(
        get_file=AsyncMock(side_effect=[
            TimeoutError(),
            SimpleNamespace(file_size=len(photo.getvalue())),
        ]),
        download=AsyncMock(side_effect=lambda source, destination: destination.write(photo.getvalue())),
    )
    stored = await service.save_telegram_photo(
        bot, "file:2", menu_id=7, role="spread"
    )
    assert stored.is_file()
    assert bot.get_file.await_count == 2
    bot.download.assert_awaited_once()
