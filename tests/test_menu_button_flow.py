"""
==========================================================
FOOD_PORN

Module: Menu Button Flow Tests
Layer: Regression Tests

Responsibilities:
    - Verify two-product home navigation
    - Verify that product selection has no redundant meal/style screen
==========================================================
"""

from app.bot.handlers.start import (get_products_menu_keyboard, get_services_keyboard, language_menu)


def _callbacks(keyboard) -> list[str | None]:
    return [button.callback_data for row in keyboard.inline_keyboard for button in row]


def test_start_language_and_two_products_are_button_driven() -> None:
    assert len(language_menu().inline_keyboard) == 3
    keyboard = get_products_menu_keyboard(user_id=1, lang="ru")
    callbacks = _callbacks(keyboard)
    assert callbacks[:2] == ["prod_food_porn", "prod_manifestation"]
    assert callbacks == ["prod_food_porn", "prod_manifestation", "home_services"]
    services = _callbacks(get_services_keyboard(user_id=1, lang="ru"))
    assert "home_orders" in services
    assert "home_instruction" in services
    assert "home_support" in services
    assert "back_to_products" in services


def test_product_selection_has_no_redundant_meal_or_style_callbacks() -> None:
    callbacks = _callbacks(get_products_menu_keyboard(user_id=1, lang="ru"))
    assert not any(value and "breakfast" in value for value in callbacks)
    assert not any(value and "dinner" in value for value in callbacks)
    assert not any(value and "style" in value for value in callbacks)
