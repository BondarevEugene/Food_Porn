"""
==========================================================
FOOD_PORN

Module: Menu Wizard Tests
Layer: Regression Tests

Responsibilities:
    - Verify full-day menu parsing by meal headings
    - Verify markers, deduplication, and input limits
==========================================================
"""

import pytest

from app.database.models import ItemCategory
from app.services.menu_wizard import (
    SLOT_BREAKFAST,
    SLOT_DINNER,
    SLOT_LUNCH,
    SLOT_OTHER,
    infer_item_category,
    parse_menu_plan,
)


def test_full_day_menu_uses_headings_as_separators_not_dishes() -> None:
    entries = parse_menu_plan(
        "Завтрак\n- Омлет\nКофе\n\nОбед:\n1. Борщ\nСалат Цезарь\n\nУжин\nСтейк\nКрасное вино"
    )

    assert [(entry.meal_slot, entry.title) for entry in entries] == [
        (SLOT_BREAKFAST, "Омлет"),
        (SLOT_BREAKFAST, "Кофе"),
        (SLOT_LUNCH, "Борщ"),
        (SLOT_LUNCH, "Салат Цезарь"),
        (SLOT_DINNER, "Стейк"),
        (SLOT_DINNER, "Красное вино"),
    ]
    assert all(entry.title not in {"Завтрак", "Обед", "Ужин"} for entry in entries)


def test_plain_lines_without_headings_are_still_dishes() -> None:
    entries = parse_menu_plan("1) Борщ\n• Плов\nПас\nборщ")

    assert [(entry.meal_slot, entry.title) for entry in entries] == [
        (SLOT_OTHER, "Борщ"),
        (SLOT_OTHER, "Плов"),
    ]


def test_full_day_menu_rejects_excess_items() -> None:
    with pytest.raises(ValueError, match="no more than 3"):
        parse_menu_plan("a\nb\nc\nd", max_items=3, language="en")


def test_ukrainian_and_english_headings_are_recognized() -> None:
    entries = parse_menu_plan("Сніданок\nСирники\nLunch\nSoup\nВечеря\nРиба")

    assert [entry.meal_slot for entry in entries] == [
        SLOT_BREAKFAST,
        SLOT_LUNCH,
        SLOT_DINNER,
    ]


def test_transliteration_typos_and_mixed_language_dishes_are_supported() -> None:
    entries = parse_menu_plan(
        "Zavtrk\nСирники з vyshneyu\nObid\nBorshch український\nVecherya\nChicken Kyiv"
    )

    assert [(entry.meal_slot, entry.title) for entry in entries] == [
        (SLOT_BREAKFAST, "Сирники з vyshneyu"),
        (SLOT_LUNCH, "Borshch український"),
        (SLOT_DINNER, "Chicken Kyiv"),
    ]


def test_european_meal_headings_are_supported() -> None:
    entries = parse_menu_plan(
        "Frühstück\nOmelett\nDéjeuner\nSoupe à l'oignon\nCena\nPasta"
    )

    assert [entry.meal_slot for entry in entries] == [
        SLOT_BREAKFAST,
        SLOT_LUNCH,
        SLOT_DINNER,
    ]


def test_category_inference_is_multilingual_and_does_not_find_tea_in_steak() -> None:
    assert infer_item_category("Стейк") == ItemCategory.MAIN
    assert infer_item_category("Kofe") == ItemCategory.DRINK
    assert infer_item_category("Caffè") == ItemCategory.DRINK
    assert infer_item_category("Soupe à l'oignon") == ItemCategory.SOUP
    assert infer_item_category("Gelato") == ItemCategory.DESSERT
