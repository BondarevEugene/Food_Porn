from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import admin
from app.config import Settings


@pytest.mark.asyncio
async def test_admin_middleware_denies_non_admin(monkeypatch):
    monkeypatch.setattr(admin, "get_settings", lambda: Settings(_env_file=None, admin_telegram_ids=(42,)))
    handler = AsyncMock()

    class Request:
        from_user = type("User", (), {"id": 12})()
        answer = AsyncMock()

    event = Request()
    await admin.AdminOnly()(handler, event, {})
    handler.assert_not_awaited()
    event.answer.assert_awaited_once()
