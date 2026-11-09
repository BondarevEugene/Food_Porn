"""Photo recovery does not spend AI calls and reuses valid files."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.menu_photo_recovery import restore_missing_menu_photos


def menu(cover: str | None, spread: str | None, cover_id=None, spread_id=None):
    return SimpleNamespace(
        id=92,
        cover_photo_path=cover,
        spread_photo_path=spread,
        cover_telegram_file_id=cover_id,
        spread_telegram_file_id=spread_id,
    )


@pytest.mark.asyncio
async def test_existing_photos_skip_telegram(tmp_path: Path, monkeypatch) -> None:
    cover = tmp_path / "cover.jpg"
    spread = tmp_path / "spread.jpg"
    cover.write_bytes(b"existing")
    spread.write_bytes(b"existing")
    download = AsyncMock()
    monkeypatch.setattr(
        "app.services.menu_photo_recovery.StorageService",
        lambda settings: SimpleNamespace(save_telegram_photo=download),
    )
    repo = SimpleNamespace(set_photos=AsyncMock())
    await restore_missing_menu_photos(
        menu(str(cover), str(spread)), None, SimpleNamespace(), repo
    )
    download.assert_not_awaited()
    repo.set_photos.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_photo_restores_and_updates_database(tmp_path: Path, monkeypatch) -> None:
    restored = tmp_path / "recovered.jpg"
    restored.write_bytes(b"restored")
    download = AsyncMock(return_value=restored)
    monkeypatch.setattr(
        "app.services.menu_photo_recovery.StorageService",
        lambda settings: SimpleNamespace(save_telegram_photo=download),
    )
    repo = SimpleNamespace(set_photos=AsyncMock())
    current = menu(None, str(restored), cover_id="telegram-file")
    await restore_missing_menu_photos(current, None, SimpleNamespace(), repo)
    download.assert_awaited_once()
    repo.set_photos.assert_awaited_once_with(92, cover=str(restored))
    assert current.cover_photo_path == str(restored)


@pytest.mark.asyncio
async def test_missing_file_id_fails_before_download(monkeypatch) -> None:
    download = AsyncMock()
    monkeypatch.setattr(
        "app.services.menu_photo_recovery.StorageService",
        lambda settings: SimpleNamespace(save_telegram_photo=download),
    )
    with pytest.raises(RuntimeError, match="must upload"):
        await restore_missing_menu_photos(
            menu(None, None), None, SimpleNamespace(),
            SimpleNamespace(set_photos=AsyncMock()),
        )
    download.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_failure_requires_reupload(monkeypatch) -> None:
    download = AsyncMock(side_effect=RuntimeError("expired"))
    monkeypatch.setattr(
        "app.services.menu_photo_recovery.StorageService",
        lambda settings: SimpleNamespace(save_telegram_photo=download),
    )
    with pytest.raises(RuntimeError, match="request reupload"):
        await restore_missing_menu_photos(
            menu(None, None, cover_id="bad"),
            None,
            SimpleNamespace(),
            SimpleNamespace(set_photos=AsyncMock()),
        )
