"""
==========================================================
FOOD_PORN

Module: Dish Input Normalization
Layer: Application Services

Responsibilities:
    - Parse a free-form list of dishes
    - Normalize structured and simplified menu input
    - Infer a practical dish category without an AI request
    - Enforce shared menu limits for Telegram and Mini App
==========================================================
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.database.models import ItemCategory

MIN_DISHES = 1
MAX_DISHES = 18
MIN_TITLE_LENGTH = 2
MAX_TITLE_LENGTH = 180

_LIST_PREFIX = re.compile(r"^\s*(?:[-*•–—]+|\d{1,2}[.)-])\s*")
_SPACES = re.compile(r"\s+")

_CATEGORY_LABELS: dict[str, ItemCategory] = {
    "main": ItemCategory.MAIN,
    "основное": ItemCategory.MAIN,
    "основна": ItemCategory.MAIN,
    "основное блюдо": ItemCategory.MAIN,
    "основна страва": ItemCategory.MAIN,
    "appetizer": ItemCategory.APPETIZER,
    "закуска": ItemCategory.APPETIZER,
    "закуски": ItemCategory.APPETIZER,
    "salad": ItemCategory.SALAD,
    "салат": ItemCategory.SALAD,
    "салати": ItemCategory.SALAD,
    "soup": ItemCategory.SOUP,
    "суп": ItemCategory.SOUP,
    "первое": ItemCategory.SOUP,
    "перша страва": ItemCategory.SOUP,
    "dessert": ItemCategory.DESSERT,
    "десерт": ItemCategory.DESSERT,
    "десерти": ItemCategory.DESSERT,
    "drink": ItemCategory.DRINK,
    "напиток": ItemCategory.DRINK,
    "напої": ItemCategory.DRINK,
    "напій": ItemCategory.DRINK,
}

_CATEGORY_KEYWORDS: tuple[tuple[ItemCategory, tuple[str, ...]], ...] = (
    (
        ItemCategory.DRINK,
        (
            "вино", "wine", "шампан", "champagne", "коктейл", "cocktail",
            "лимонад", "lemonade", "компот", "сок", "juice", "чай", "tea",
            "кофе", "кава", "coffee", "вода", "water", "виски", "whisky",
        ),
    ),
    (
        ItemCategory.DESSERT,
        (
            "десерт", "dessert", "торт", "cake", "тирамису", "tiramisu",
            "чизкейк", "cheesecake", "морожен", "морозив", "ice cream",
            "панна-кот", "брауни", "brownie", "блинчик", "млинц",
        ),
    ),
    (ItemCategory.SOUP, ("суп", "soup", "борщ", "уха", "юшк", "солянк", "окрошк")),
    (ItemCategory.SALAD, ("салат", "salad", "цезар", "оливье", "олів'є", "винегрет")),
    (
        ItemCategory.APPETIZER,
        (
            "закуск", "appetizer", "bruschetta", "брускет", "канап", "тарталет",
            "нарезк", "нарізк", "паштет", "рулетик", "сырная тарелка",
            "сирна тарілка",
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class NormalizedDish:
    """Validated menu item ready for persistence."""

    title: str
    category: ItemCategory


def clean_dish_title(value: str) -> str:
    """Remove list numbering and collapse accidental whitespace."""
    title = _LIST_PREFIX.sub("", value.strip())
    return _SPACES.sub(" ", title).strip()


def _explicit_category(title: str) -> tuple[ItemCategory | None, str]:
    """Read optional prefixes such as ``Десерт: тирамису``."""
    match = re.match(r"^\s*([^:]{2,30})\s*:\s*(.+)$", title)
    if not match:
        return None, title
    category = _CATEGORY_LABELS.get(match.group(1).strip().casefold())
    return (category, match.group(2).strip()) if category else (None, title)


def infer_dish_category(title: str) -> ItemCategory:
    """Infer a layout category locally; unknown dishes safely become mains."""
    normalized = title.casefold().replace("ё", "е")
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return category
    return ItemCategory.MAIN


def parse_free_dish_list(raw: str) -> list[NormalizedDish]:
    """Parse one dish per line; semicolons are also accepted as separators."""
    if not isinstance(raw, str):
        raise ValueError("Dish list must be text")
    entries = [part for part in re.split(r"[\r\n;]+", raw) if part.strip()]
    return normalize_dish_payload(entries)


def normalize_dish_payload(payload: Any) -> list[NormalizedDish]:
    """Normalize both structured rows and the simple list submitted by clients."""
    if not isinstance(payload, list) or not MIN_DISHES <= len(payload) <= MAX_DISHES:
        raise ValueError(f"Add {MIN_DISHES}–{MAX_DISHES} dishes")

    normalized: list[NormalizedDish] = []
    for entry in payload:
        if isinstance(entry, str):
            raw_title = entry
            raw_category = None
        elif isinstance(entry, dict):
            raw_title = entry.get("title")
            raw_category = entry.get("category")
        else:
            raise ValueError("Each dish must be text or an object")

        if not isinstance(raw_title, str):
            raise ValueError("Dish title must be text")

        title = clean_dish_title(raw_title)
        explicit_category, title = _explicit_category(title)
        if not MIN_TITLE_LENGTH <= len(title) <= MAX_TITLE_LENGTH:
            raise ValueError(f"Dish title must contain {MIN_TITLE_LENGTH}–{MAX_TITLE_LENGTH} characters")

        if raw_category is None or raw_category == "":
            category = explicit_category or infer_dish_category(title)
        else:
            try:
                category = ItemCategory(str(raw_category).lower())
            except ValueError as exc:
                raise ValueError(f"Unknown dish category: {raw_category}") from exc

        normalized.append(NormalizedDish(title=title, category=category))

    return normalized
