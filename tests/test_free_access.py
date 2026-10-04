"""Authorized users can render when Portmone is unavailable."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.bot.handlers import wallpaper
from app.config import Settings
from app.services import free_access, settings_service


class SessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return object()

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_free_ids_and_existing_vip_usernames(monkeypatch):
    settings = Settings(_env_file=None, free_generation_telegram_ids=(42,))
    factory = SessionFactory()
    assert await free_access.has_free_generation_access(42, None, settings, factory)
    assert not await free_access.has_free_generation_access(43, None, settings, factory)

    seen = []

    async def vip_list(session, defaults):
        seen.append(defaults)
        return ["@Bondarev_E", "friend"]

    monkeypatch.setattr(free_access, "get_vip_users", vip_list)
    assert await free_access.has_free_generation_access(43, "BONDAREV_E", settings, factory)
    assert not await free_access.has_free_generation_access(43, "stranger", settings, factory)
    assert seen[0] == settings.default_vip_users


@pytest.mark.asyncio
async def test_configured_vip_list_replaces_defaults(monkeypatch):
    async def value(session, key, default):
        assert key == "vip_usernames" and "bondarev_e" in default
        return "Friend, AnotherFriend"

    monkeypatch.setattr(settings_service, "get_setting", value)
    users = await settings_service.get_vip_users(SimpleNamespace(), ["bondarev_e"])
    assert users == ["Friend", "AnotherFriend"]


@pytest.mark.asyncio
async def test_no_free_access_and_no_payment_keeps_uploads(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, storage_root=tmp_path)
    photo = settings.uploads_dir / "wallpapers" / "42" / "portrait.jpg"
    photo.parent.mkdir(parents=True)
    Image.new("RGB", (440, 540), "#987654").save(photo)
    message = SimpleNamespace(from_user=SimpleNamespace(id=42, username=None), answer=AsyncMock())
    state = SimpleNamespace(get_data=AsyncMock(return_value={
        "lang": "ru", "goals": ["A", "B", "C", "D", "E"],
    }), set_state=AsyncMock())
    monkeypatch.setattr(wallpaper, "PaymentService", lambda _settings: SimpleNamespace(portmone_ready=False))
    await wallpaper.generate_wallpapers(message, state, settings, None)
    assert photo.is_file()
    assert "бесплатный доступ не настроен" in message.answer.await_args.args[0]
