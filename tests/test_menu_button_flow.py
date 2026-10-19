"""
==========================================================
FOOD_PORN

Module: Menu Button Flow Tests
Layer: Regression Tests

Responsibilities:
    - Verify two-product home navigation
    - Verify the direct meal selection screen
==========================================================
"""

from app.bot.handlers.menu import build_meal_keyboard
from app.bot.handlers.start import get_products_menu_keyboard, language_menu


def _callbacks(keyboard) -> list[str | None]:
    return [button.callback_data for row in keyboard.inline_keyboard for button in row]


def test_start_language_and_two_products_are_button_driven() -> None:
    assert len(language_menu().inline_keyboard) == 3
    keyboard = get_products_menu_keyboard(user_id=1, lang="ru")
    callbacks = _callbacks(keyboard)
    assert callbacks[:2] == ["prod_food_porn", "prod_manifestation"]
    assert "home_orders" in callbacks
    assert "home_instruction" in callbacks
    assert "home_support" in callbacks


def test_menu_setup_exposes_meals_without_an_extra_style_screen() -> None:
    meal_callbacks = _callbacks(build_meal_keyboard("ru"))
    assert any(value and "breakfast" in value for value in meal_callbacks)
    assert any(value and "dinner" in value for value in meal_callbacks)
    assert not any(value and "style" in value for value in meal_callbacks)
