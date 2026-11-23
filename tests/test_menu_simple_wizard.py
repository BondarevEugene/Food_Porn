"""The customer chooses meal and mood before dishes, without extra category screens."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import InlineKeyboardMarkup

from app.bot.handlers.menu import (
    _menu_mood_keyboard,
    begin_menu_setup,
    build_dashboard_kb,
)
from app.database.models import MenuStatus
from app.services.menu_living_scene import plan_living_scene


@pytest.mark.asyncio
async def test_menu_starts_with_meal_choice_without_creating_order():
    message = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
    await begin_menu_setup(message, state, SimpleNamespace(), "ru")
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "menu_new:breakfast" in callbacks
    assert "menu_new:dinner" in callbacks


def test_mood_keyboard_offers_five_real_options():
    markup = _menu_mood_keyboard(42)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert len(callbacks) == 5
    assert all("set_mood" in value for value in callbacks)


def test_draft_has_direct_dish_input_and_no_category_step():
    menu = SimpleNamespace(
        id=42, items=[], cover_photo_path=None, spread_photo_path=None,
        status=MenuStatus.DRAFT, is_paid=False,
    )
    markup = build_dashboard_kb(menu)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert any("bulk_items" in value for value in callbacks)
    assert not any("pick_category" in value for value in callbacks)
    assert any("choose_mood" in value for value in callbacks)


@pytest.mark.parametrize("meal,theme", [("breakfast", "light"), ("dinner", "dark")])
def test_mood_changes_scene_without_changing_meal_palette(meal, theme):
    family = plan_living_scene(meal=meal, mood="family", order_seed=42)
    festive = plan_living_scene(meal=meal, mood="festive", order_seed=42)
    assert family.visual_theme == festive.visual_theme == theme
    assert family.wardrobe != festive.wardrobe
