"""Slow Telegram status notifications must not block receiving menu photos."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.menu import _photo_status_notice


@pytest.mark.asyncio
async def test_menu_photo_receipt_timeout_is_nonfatal():
    message = SimpleNamespace(answer=AsyncMock(side_effect=TimeoutError()))
    await _photo_status_notice(message, "Получено, загружаю")
    message.answer.assert_awaited_once_with("Получено, загружаю")


@pytest.mark.asyncio
async def test_menu_photo_receipt_is_sent_when_available():
    message = SimpleNamespace(answer=AsyncMock())
    await _photo_status_notice(message, "Получено, загружаю")
    message.answer.assert_awaited_once_with("Получено, загружаю")
