"""Safety regression tests for Telegram book delivery callbacks."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.bot.handlers.little_legend import send_little_legend_book
from app.little_legend.book_delivery import DeliveryStatus


def callback_for(story_id: str = "12") -> Mock:
    callback = Mock()
    callback.data = f"ll_send:{story_id}"
    callback.from_user.id = 42
    callback.message.chat.id = 42
    callback.message.chat.type = "private"
    callback.answer = AsyncMock()
    callback.message.answer = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_invalid_callback_rejected_without_storage() -> None:
    callback = callback_for("invalid")
    with patch(
        "app.bot.handlers.little_legend.configured_private_pdf_store",
    ) as store:
        await send_little_legend_book(callback)
    store.assert_not_called()
    callback.answer.assert_awaited_once_with(
        "Invalid book", show_alert=True,
    )


@pytest.mark.asyncio
async def test_group_callback_rejected_without_storage() -> None:
    callback = callback_for()
    callback.message.chat.type = "supergroup"
    with patch(
        "app.bot.handlers.little_legend.configured_private_pdf_store",
    ) as store:
        await send_little_legend_book(callback)
    store.assert_not_called()
    callback.answer.assert_awaited_once_with(
        "Open this in a private chat", show_alert=True,
    )


@pytest.mark.asyncio
async def test_different_private_chat_rejected_without_storage() -> None:
    callback = callback_for()
    callback.message.chat.id = 99
    with patch(
        "app.bot.handlers.little_legend.configured_private_pdf_store",
    ) as store:
        await send_little_legend_book(callback)
    store.assert_not_called()
    callback.answer.assert_awaited_once_with(
        "Open your own private chat", show_alert=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [DeliveryStatus.SENT, DeliveryStatus.UNCERTAIN])
async def test_terminal_release_cannot_be_sent_again(status: DeliveryStatus) -> None:
    callback = callback_for()
    session = AsyncMock()
    result = Mock()
    result.scalar_one_or_none.return_value = 12
    session.execute.return_value = result
    factory = Mock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    with (
        patch("app.bot.handlers.little_legend.async_session_maker", factory),
        patch(
            "app.bot.handlers.little_legend.get_release_manifest",
            new_callable=AsyncMock, return_value=Mock(status=status),
        ),
        patch(
            "app.bot.handlers.little_legend.send_owned_release",
            new_callable=AsyncMock,
        ) as send,
        patch("app.bot.handlers.little_legend.configured_private_pdf_store") as store,
    ):
        await send_little_legend_book(callback)
    store.assert_not_called()
    send.assert_not_awaited()
    callback.answer.assert_awaited_once_with(
        "Book is not ready for delivery", show_alert=True,
    )


@pytest.mark.asyncio
async def test_missing_storage_prevents_dispatch() -> None:
    callback = callback_for()
    session = AsyncMock()
    result = Mock()
    result.scalar_one_or_none.return_value = 12
    session.execute.return_value = result
    factory = Mock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    with (
        patch("app.bot.handlers.little_legend.async_session_maker", factory),
        patch(
            "app.bot.handlers.little_legend.get_release_manifest",
            new_callable=AsyncMock,
            return_value=Mock(status=DeliveryStatus.READY),
        ),
        patch(
            "app.bot.handlers.little_legend.configured_private_pdf_store",
            side_effect=ValueError("not configured"),
        ),
        patch(
            "app.bot.handlers.little_legend.send_owned_release",
            new_callable=AsyncMock,
        ) as send,
    ):
        await send_little_legend_book(callback)
    send.assert_not_awaited()
    callback.answer.assert_awaited_once_with(
        "Delivery storage is not configured", show_alert=True,
    )


@pytest.mark.asyncio
async def test_dispatch_reservation_conflict_does_not_retry() -> None:
    callback = callback_for()
    session = AsyncMock()
    result = Mock()
    result.scalar_one_or_none.return_value = 12
    session.execute.return_value = result
    factory = Mock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    with (
        patch("app.bot.handlers.little_legend.async_session_maker", factory),
        patch(
            "app.bot.handlers.little_legend.get_release_manifest",
            new_callable=AsyncMock,
            return_value=Mock(status=DeliveryStatus.READY),
        ),
        patch("app.bot.handlers.little_legend.configured_private_pdf_store"),
        patch(
            "app.bot.handlers.little_legend.send_owned_release",
            new_callable=AsyncMock,
            side_effect=PermissionError("effect already reserved"),
        ) as send,
    ):
        await send_little_legend_book(callback)
    send.assert_awaited_once()
    callback.message.answer.assert_awaited_once()
    assert "No duplicate" in callback.message.answer.call_args.args[0]
