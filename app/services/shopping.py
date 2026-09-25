"""
==========================================================
FOOD_PORN

Module: Shopping List Aggregator
Layer: Service

Responsibilities:
    - Aggregate and normalize ingredients from all menu dishes
    - Produce a clean consolidated shopping list
==========================================================
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def aggregate_shopping_list(menu_details: dict[str, Any]) -> list[str]:
    """
    Суммирует одинаковые ингредиенты из всех блюд для формирования списка покупок.
    """
    shopping_bag = defaultdict(list)

    for dish_data in menu_details.values():
        ingredients = dish_data.get("ingredients", [])
        for item in ingredients:
            parts = item.split("-")
            name = parts[0].strip().capitalize()
            amount = parts[1].strip() if len(parts) > 1 else "за смаком"
            shopping_bag[name].append(amount)

    result = []
    for name, amounts in shopping_bag.items():
        result.append(f"• {name}: {', '.join(amounts)}")

    return result