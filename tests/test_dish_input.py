"""
==========================================================
FOOD_PORN

Module: Dish Input Tests
Layer: Quality Assurance

Responsibilities:
    - Verify free-list parsing
    - Verify automatic category inference
    - Preserve compatibility with structured menu rows
==========================================================
"""

from __future__ import annotations

import pytest
from app.database.models import ItemCategory
from app.services.dish_input import normalize_dish_payload, parse_free_dish_list


def test_free_list_removes_numbering_and_infers_categories() -> None:
    dishes = parse_free_dish_list(
        "1. Борщ с телятиной\n"
        "2) Салат Цезарь\n"
        "• Тирамису\n"
        "- Лимонад с мятой"
    )

    assert [dish.title for dish in dishes] == [
        "Борщ с телятиной",
        "Салат Цезарь",
        "Тирамису",
        "Лимонад с мятой",
    ]
    assert [dish.category for dish in dishes] == [
        ItemCategory.SOUP,
        ItemCategory.SALAD,
        ItemCategory.DESSERT,
        ItemCategory.DRINK,
    ]


def test_explicit_prefix_overrides_inference_and_is_removed() -> None:
    [dish] = parse_free_dish_list("Закуска: тартар из лосося")

    assert dish.title == "тартар из лосося"
    assert dish.category == ItemCategory.APPETIZER


def test_structured_rows_keep_the_selected_category() -> None:
    [dish] = normalize_dish_payload([{"category": "main", "title": "Кофейный стейк"}])

    assert dish.title == "Кофейный стейк"
    assert dish.category == ItemCategory.MAIN


@pytest.mark.parametrize("payload", [[], ["a"], ["Блюдо"] * 19, [{"title": 123}]])
def test_invalid_lists_are_rejected(payload: object) -> None:
    with pytest.raises(ValueError):
        normalize_dish_payload(payload)
