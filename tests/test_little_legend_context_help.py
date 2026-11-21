"""Contextual stage help contracts: concise, reversible, no paid side effects."""
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiogram.types import InlineKeyboardButton

from app.bot.handlers.little_legend_context_help import (
    help_button,
    stage_message,
    toggle_stage_help,
)


@pytest.mark.parametrize("stage", ["outline", "art", "release"])
@pytest.mark.parametrize("lang", ["uk", "ru", "en"])
def test_stage_guidance_has_short_and_expanded_text(stage, lang):
    short = stage_message(lang, stage)
    full = stage_message(lang, stage, expanded=True)
    assert full.startswith(short)
    assert len(full) > len(short)
    assert "ⓘ" in full
    assert help_button(lang, stage, 23).callback_data == f"ll_context:{stage}:23:show"


@pytest.mark.asyncio
async def test_context_toggle_preserves_existing_action_buttons():
    callback = Mock()
    callback.from_user.id = 77
    callback.data = "ll_context:release:23:show"
    callback.message.chat.type = "private"
    callback.message.chat.id = 77
    callback.message.html_text = "Ready\n\n" + stage_message("ru", "release")
    callback.message.reply_markup.inline_keyboard = [
        [InlineKeyboardButton(text="Prepare", callback_data="ll_prepare:23")],
        [help_button("ru", "release", 23)],
        [InlineKeyboardButton(text="Book", callback_data="ll_book:23")],
    ]
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    session = AsyncMock()
    session.execute.return_value.scalar_one_or_none.return_value = 23
    factory = Mock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    with (
        patch(
            "app.bot.handlers.little_legend_context_help.async_session_maker",
            factory,
        ),
        patch(
            "app.bot.handlers.little_legend_context_help.selected_language",
            new=AsyncMock(return_value="ru"),
        ),
    ):
        await toggle_stage_help(callback)
    message = callback.message.edit_text.await_args.args[0]
    keyboard = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert "ⓘ" in message
    assert keyboard.inline_keyboard[0][0].callback_data == "ll_prepare:23"
    assert keyboard.inline_keyboard[-1][0].callback_data == "ll_book:23"
    assert keyboard.inline_keyboard[1][0].callback_data == "ll_context:release:23:hide"
    callback.message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_context_request_does_not_touch_database():
    callback = Mock()
    callback.data = "ll_context:art:invalid:show"
    callback.from_user.id = 77
    callback.message.chat.type = "private"
    callback.message.chat.id = 77
    callback.answer = AsyncMock()
    with patch(
        "app.bot.handlers.little_legend_context_help.async_session_maker"
    ) as factory:
        await toggle_stage_help(callback)
        factory.assert_not_called()
    callback.message.edit_text.assert_not_called()
