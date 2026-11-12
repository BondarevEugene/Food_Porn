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


@pytest.mark.asyncio
async def test_repeated_admin_overview_click_is_a_noop(monkeypatch):
    from types import SimpleNamespace

    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import EditMessageText

    monkeypatch.setattr(admin, "summary_text", AsyncMock(return_value="Overview"))
    monkeypatch.setattr(admin, "get_admin_main_keyboard", lambda: None)
    message = SimpleNamespace(
        edit_text=AsyncMock(
            side_effect=TelegramBadRequest(
                method=EditMessageText(chat_id=1, message_id=1, text="Overview"),
                message="Bad Request: message is not modified",
            )
        )
    )
    callback = SimpleNamespace(answer=AsyncMock(), message=message)
    state = SimpleNamespace(clear=AsyncMock())

    await admin.admin_home_callback(callback, state)
    callback.answer.assert_awaited_once()
    state.clear.assert_awaited_once()
    message.edit_text.assert_awaited_once()
