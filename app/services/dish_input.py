"""
==========================================================
FOOD_PORN

Module: Flexible Dish Input
Layer: Domain Service

Accepts either categorized rows or a plain human-written dish list.
Category inference is deterministic and does not create an extra AI request.
==========================================================
"""

from __future__ import annotations

import re
from typing import Any

from app.database.models import ItemCategory

SKIP_WORDS = {"пас", "pass", "skip", "пропустить", "пропустити", "—", "-"}
DEFAULT_SEQUENCE = (
    ItemCategory.MAIN,
    ItemCategory.APPETIZER,
    ItemCategory.DESSERT,
    ItemCategory.DRINK,
)
CATEGORY_WORDS = {
    ItemCategory.MAIN: {"main", "основное", "основна", "основне", "горячее", "гаряче"},
    ItemCategory.APPETIZER: {"appetizer", "starter", "закуска", "закуски"},
    ItemCategory.SALAD: {"salad", "салат", "салаты", "салати"},
    ItemCategory.SOUP: {"soup", "суп", "супы", "супи"},
    ItemCategory.DESSERT: {"dessert", "десерт", "десерты", "десерти"},
    ItemCategory.DRINK: {"drink", "drinks", "напиток", "напитки", "напій", "напої"},
}


def _clean_title(value: str) -> str:
    value = re.sub(r"^\s*(?:[-*•·]+|\d+[.)])\s*", "", value.strip())
    return re.sub(r"\s+", " ", value).strip(" ,;–—")


def _category_and_title(value: str, position: int) -> tuple[ItemCategory, str]:
    prefix, separator, rest = value.partition(":")
    if separator:
        normalized = prefix.strip().casefold()
        for category, words in CATEGORY_WORDS.items():
            if normalized in words:
                return category, _clean_title(rest)
    return DEFAULT_SEQUENCE[position % len(DEFAULT_SEQUENCE)], _clean_title(value)


def _validate(items: list[dict[str, str]]) -> list[dict[str, str]]:
    if not 1 <= len(items) <= 18:
        raise ValueError("Add from 1 to 18 dishes")
    for item in items:
        if item["category"] not in ItemCategory._value2member_map_:
            raise ValueError("Unknown dish category")
        if not 2 <= len(item["title"]) <= 180:
            raise ValueError("Dish title must contain from 2 to 180 characters")
    return items


def normalize_dish_payload(payload: Any) -> list[dict[str, str]]:
    """Normalize the two supported Mini App input modes to categorized rows."""
    if isinstance(payload, list):
        rows: list[dict[str, str]] = []
        for raw in payload:
            if not isinstance(raw, dict):
                raise ValueError("Dish row must be an object")
            title = _clean_title(str(raw.get("title") or ""))
            if title.casefold() in SKIP_WORDS:
                continue
            rows.append({"category": str(raw.get("category") or ""), "title": title})
        return _validate(rows)

    if isinstance(payload, dict) and payload.get("mode") == "list":
        values = re.split(r"[\n;,]+", str(payload.get("text") or ""))
        rows = []
        for raw in values:
            title = _clean_title(raw)
            if not title or title.casefold() in SKIP_WORDS:
                continue
            category, title = _category_and_title(title, len(rows))
            if title and title.casefold() not in SKIP_WORDS:
                rows.append({"category": category.value, "title": title})
        return _validate(rows)

    raise ValueError("Unknown dish input mode")
