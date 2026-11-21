"""Regression contracts for Little Legend's customer-facing navigation."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.bot.handlers.little_legend import (
    little_legend_language,
    open_little_legend,
    show_little_legend_help,
)


def _callback():
    callback = Mock()
    callback.from_user.id = 101
    callback.from_user.language_code = "uk"
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_selected_russian_language_controls_book_menu():
    callback = _callback()
    with (
        patch(
            "app.bot.handlers.little_legend.little_legend_language",
            new=AsyncMock(return_value="ru"),
        ),
        patch(
            "app.bot.handlers.little_legend.get_settings",
        ) as settings,
    ):
        settings.return_value.miniapp_url = "https://example.org/miniapp"
        await open_little_legend(callback)
    text = callback.message.answer.await_args.args[0]
    keyboard = callback.message.answer.await_args.kwargs["reply_markup"]
    labels = [row[0].text for row in keyboard.inline_keyboard]
    assert "персональная книга" in text
    assert "Создать книгу" in " ".join(labels)
    assert "Форматы и цены" in " ".join(labels)
    assert "Как создать книгу" in " ".join(labels)
    assert "Мої" not in " ".join(labels)


@pytest.mark.asyncio
async def test_help_explains_editor_vs_creation_in_selected_language():
    callback = _callback()
    with patch(
        "app.bot.handlers.little_legend.little_legend_language",
        new=AsyncMock(return_value="ru"),
    ):
        await show_little_legend_help(callback)
    message = callback.message.answer.await_args.args[0]
    assert "Создать книгу" in message
    assert "Редактор книги" in message
    assert "не отдельный платный формат" in message
    assert "Мои книги" in message
    assert "Оплата пока недоступна" in message


@pytest.mark.asyncio
async def test_language_falls_back_to_telegram_when_no_customer():
    user = Mock(id=None, language_code="en-US")
    assert await little_legend_language(user) == "en"
