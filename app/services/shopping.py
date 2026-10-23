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
from decimal import Decimal, InvalidOperation
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


AISLE_ORDER = (
    "produce", "meat_fish", "dairy", "bakery", "pantry", "drinks", "frozen", "other"
)


def aggregate_shopping_sections(menu_details: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Merge structured quantities while keeping pantry staples visibly separate."""
    merged: dict[tuple[str, str, str, bool], Decimal] = defaultdict(Decimal)
    labels: dict[tuple[str, str, str, bool], str] = {}
    for dish in menu_details.values():
        if not isinstance(dish, dict):
            continue
        for raw in dish.get("shopping_items") or []:
            if not isinstance(raw, dict) or not str(raw.get("name") or "").strip():
                continue
            aisle = str(raw.get("aisle") or "other")
            if aisle not in AISLE_ORDER:
                aisle = "other"
            name = str(raw["name"]).strip()
            unit = str(raw.get("unit") or "").strip()
            pantry = bool(raw.get("pantry"))
            key = (name.casefold(), unit.casefold(), aisle, pantry)
            labels[key] = name
            try:
                amount = Decimal(str(raw.get("amount") or 0))
            except InvalidOperation:
                amount = Decimal(0)
            merged[key] += max(amount, Decimal(0))
    sections: dict[str, list[dict[str, Any]]] = {}
    for aisle in AISLE_ORDER:
        rows = []
        for key, amount in merged.items():
            _, unit, item_aisle, pantry = key
            if item_aisle != aisle:
                continue
            rows.append({
                "name": labels[key],
                "amount": format(amount.normalize(), "f") if amount else "",
                "unit": unit,
                "pantry": pantry,
            })
        if rows:
            sections[aisle] = sorted(rows, key=lambda item: item["name"].casefold())
    return sections
