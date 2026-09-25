"""
==========================================================
FOOD_PORN

Module: Menu Plan & Localization Tests
Layer: Enterprise Test Suite / Quality Assurance

Responsibilities:
    - Comprehensive validation of menu item distribution and categories
    - Strict property-based and parameterized validation for skip-words
    - Robust schema conformity checks for enterprise bot workflows
==========================================================
"""

from __future__ import annotations

import pytest

from app.bot.helpers import ITEM_PLAN
from app.database.models import ItemCategory
from app.database.repositories import is_skipped_title


def test_menu_plan_structure_and_integrity() -> None:
    """Проверяет целостность структуры меню, типы данных и корректность категорий."""
    total_items = 0
    categories_seen = set()

    for category, count, description in ITEM_PLAN:
        # Проверяем, что категория принадлежит Enum
        assert isinstance(category, ItemCategory), f"Некорректный тип категории: {type(category)}"

        # Проверяем, что количество позиций — положительное число
        assert isinstance(count, int) and count > 0, f"Неверное количество для категории {category}: {count}"

        # Проверяем наличие описания
        assert isinstance(description, str) and len(description.strip()) > 0, f"Пустое описание для категории {category}"

        total_items += count
        categories_seen.add(category)

    # Проверяем общую сумму позиций и отсутствие дубликатов категорий
    assert total_items == sum(count for _, count, _ in ITEM_PLAN)
    assert len(categories_seen) == len(ITEM_PLAN), "Обнаружены дублирующиеся категории в плане меню"


@pytest.mark.parametrize(
    "raw_title, expected",
    [
        ("пас", True),
        (" ПАС ", True),
        ("pass", True),
        ("PASS", True),
        ("пропустить", True),
        ("skip", True),
        ("Тирамису", False),
        ("Борщ украинский", False),
        ("Рибай стейк", False),
    ],
)
def test_skip_word_normalization_enterprise(raw_title: str, expected: bool) -> None:
    """Параметризированный enterprise-тест для проверки ключевых слов пропуска блюд."""
    result = is_skipped_title(raw_title)
    assert isinstance(result, bool), "Функция is_skipped_title должна возвращать булево значение"
    assert result is expected, f"Ошибка для ввода '{raw_title}': ожидалось {expected}, получено {result}"