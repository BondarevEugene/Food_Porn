"""Regression contracts for Little Legend's customer-facing navigation."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.bot.handlers.little_legend import (
    little_legend_language,
    open_little_legend,
    show_little_legend_help,
    toggle_little_legend_home_help,
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
    assert "Ваш ребёнок — герой книги" in text
    assert "Создать книгу" in " ".join(labels)
    assert "Форматы и цены" not in " ".join(labels)
    assert "Что здесь делать?" in " ".join(labels)
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


@pytest.mark.asyncio
async def test_context_help_expands_in_same_message_without_new_message():
    callback = _callback()
    callback.data = "ll_home:help"
    callback.message.edit_text = AsyncMock()
    with (
        patch(
            "app.bot.handlers.little_legend.little_legend_language",
            new=AsyncMock(return_value="ru"),
        ),
        patch("app.bot.handlers.little_legend.get_settings") as settings,
    ):
        settings.return_value.miniapp_url = "https://example.org/miniapp"
        await toggle_little_legend_home_help(callback)
    callback.message.answer.assert_not_awaited()
    message = callback.message.edit_text.await_args.args[0]
    keyboard = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert "Подсказка" in message
    assert "Скрыть подсказку" in str(keyboard.inline_keyboard)
    assert "Форматы и цены" in str(keyboard.inline_keyboard)


@pytest.mark.asyncio
async def test_context_help_collapses_without_losing_navigation():
    callback = _callback()
    callback.data = "ll_home:hide"
    callback.message.edit_text = AsyncMock()
    with (
        patch(
            "app.bot.handlers.little_legend.little_legend_language",
            new=AsyncMock(return_value="ru"),
        ),
        patch("app.bot.handlers.little_legend.get_settings") as settings,
    ):
        settings.return_value.miniapp_url = "https://example.org/miniapp"
        await toggle_little_legend_home_help(callback)
    message = callback.message.edit_text.await_args.args[0]
    keyboard = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert "Подсказка" not in message
    assert "Создать книгу" in str(keyboard.inline_keyboard)
