"""Menu callback recovery must never swallow supported actions."""
from unittest.mock import AsyncMock, Mock

import pytest

from app.bot.handlers.menu import MenuAction, router, unknown_menu_callback


def test_menu_callback_fallback_registered_last():
    callbacks = router.callback_query.handlers
    assert callbacks[-1].callback is unknown_menu_callback
    assert any(handler.callback.__name__ == "pick_item_category" for handler in callbacks[:-1])
    assert any(handler.callback.__name__ == "choose_cuisine" for handler in callbacks[:-1])
    assert any(handler.callback.__name__ == "prompt_menu_plan" for handler in callbacks[:-1])


def test_menu_callback_contract_keeps_category_action():
    packed = MenuAction(
        action="pick_category", menu_id=42,
    ).pack()
    assert packed.startswith("menu:pick_category:42")


@pytest.mark.asyncio
async def test_obsolete_menu_button_gets_actionable_alert():
    callback = Mock(id="test-callback")
    callback.answer = AsyncMock()
    await unknown_menu_callback(callback)
    callback.answer.assert_awaited_once()
    args, kwargs = callback.answer.await_args
    assert "/start" in args[0]
    assert "/history" in args[0]
    assert kwargs["show_alert"] is True
