"""
==========================================================
FOOD_PORN

Module: Menu Wizard Tests
Layer: Regression Tests

Responsibilities:
    - Verify breakfast and dinner category limits
    - Verify bulk input, pass, and surprise normalization
==========================================================
"""

import pytest

from app.database.models import ItemCategory
from app.services.menu_wizard import (
    MEAL_BREAKFAST,
    MEAL_DINNER,
    category_rule,
    meal_rules,
    normalize_dish_lines,
)


def test_meal_categories_follow_product_scenario() -> None:
    breakfast = meal_rules(MEAL_BREAKFAST)
    dinner = meal_rules(MEAL_DINNER)
    assert [(rule.category, rule.limit) for rule in breakfast] == [
        (ItemCategory.MAIN, 9),
        (ItemCategory.DESSERT, 3),
        (ItemCategory.DRINK, 4),
    ]
    assert [(rule.category, rule.limit) for rule in dinner] == [
        (ItemCategory.MAIN, 9),
        (ItemCategory.SALAD, 3),
        (ItemCategory.DRINK, 4),
    ]


def test_bulk_input_is_normalized_and_deduplicated() -> None:
    assert normalize_dish_lines("1. Борщ\n• Плов\nборщ", limit=9) == ["Борщ", "Плов"]
    assert normalize_dish_lines("пас", limit=4) == []
    assert normalize_dish_lines("???", limit=3, language="ru") == ["Сюрприз от повара"]


def test_bulk_input_rejects_excess_items() -> None:
    with pytest.raises(ValueError, match="no more than 3"):
        normalize_dish_lines("a\nb\nc\nd", limit=3, language="en")


def test_category_must_belong_to_selected_meal() -> None:
    assert category_rule(MEAL_BREAKFAST, ItemCategory.DESSERT).limit == 3
    with pytest.raises(ValueError):
        category_rule(MEAL_DINNER, ItemCategory.DESSERT)
