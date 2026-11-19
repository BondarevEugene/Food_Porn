"""Telegram-native Little Legend owner views."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.bot.handlers.little_legend import (
    prepare_little_legend_book,
    show_little_legend_book,
)
from app.little_legend.book_delivery import DeliveryStatus


@pytest.mark.asyncio
async def test_invalid_book_id_is_rejected_without_db_access() -> None:
    callback = Mock(data="ll_book:invalid")
    callback.answer = AsyncMock()
    with patch(
        "app.bot.handlers.little_legend.async_session_maker",
    ) as factory:
        await show_little_legend_book(callback)
    factory.assert_not_called()
    callback.answer.assert_awaited_once_with(
        "Invalid book", show_alert=True,
    )


@pytest.mark.asyncio
async def test_missing_book_does_not_query_release_manifest() -> None:
    callback = Mock(data="ll_book:123")
    callback.from_user.id = 42
    callback.answer = AsyncMock()
    session = AsyncMock()
    result = Mock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    factory = Mock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    with (
        patch("app.bot.handlers.little_legend.async_session_maker", factory),
        patch(
            "app.bot.handlers.little_legend.get_release_manifest",
            new_callable=AsyncMock,
        ) as manifest,
    ):
        await show_little_legend_book(callback)
    manifest.assert_not_awaited()
    callback.answer.assert_awaited_once_with(
        "Book not found", show_alert=True,
    )


def test_delivery_status_labels_include_all_terminal_states() -> None:
    assert DeliveryStatus.SENT.value == "sent"
    assert DeliveryStatus.UNCERTAIN.value == "uncertain"


@pytest.mark.asyncio
async def test_prepare_rejects_foreign_private_chat_before_storage() -> None:
    callback = Mock(data="ll_prepare:12")
    callback.from_user.id = 42
    callback.message.chat.type = "private"
    callback.message.chat.id = 999
    callback.answer = AsyncMock()
    with (
        patch("app.bot.handlers.little_legend.async_session_maker") as database,
        patch("app.bot.handlers.little_legend.configured_private_pdf_store") as storage,
    ):
        await prepare_little_legend_book(callback)
    database.assert_not_called()
    storage.assert_not_called()
    callback.answer.assert_awaited_once_with(
        "Book not found", show_alert=True,
    )


@pytest.mark.asyncio
async def test_prepare_invalid_story_never_touches_storage() -> None:
    callback = Mock(data="ll_prepare:invalid")
    callback.message.chat.type = "private"
    callback.answer = AsyncMock()
    with patch(
        "app.bot.handlers.little_legend.configured_generated_art_store",
    ) as storage:
        await prepare_little_legend_book(callback)
    storage.assert_not_called()
    callback.answer.assert_awaited_once_with(
        "Invalid book", show_alert=True,
    )
