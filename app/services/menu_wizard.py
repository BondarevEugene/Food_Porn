"""
==========================================================
FOOD_PORN

Module: Menu Wizard Rules
Layer: Domain Service

Responsibilities:
    - Describe breakfast and dinner category limits
    - Normalize bulk dish input without extra AI requests
    - Keep Telegram handlers free from validation details
==========================================================
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.database.models import ItemCategory

MEAL_BREAKFAST = "breakfast"
MEAL_DINNER = "dinner"

SKIP_WORDS = frozenset({"пас", "pass", "skip", "пропустить", "пропустити", "-", "—"})
SURPRISE_TITLES = {"uk": "Сюрприз від шефа", "ru": "Сюрприз от повара", "en": "Chef's surprise"}


@dataclass(frozen=True, slots=True)
class CategoryRule:
    category: ItemCategory
    limit: int
    labels: dict[str, str]

    def label(self, language: str) -> str:
        return self.labels.get(language, self.labels["ru"])


MAIN_RULE = CategoryRule(ItemCategory.MAIN, 9, {"uk": "Основні страви", "ru": "Основные блюда", "en": "Main dishes"})
BREAKFAST_SWEET_RULE = CategoryRule(ItemCategory.DESSERT, 3, {"uk": "Солодкі сніданки", "ru": "Сладкие завтраки", "en": "Sweet breakfasts"})
DINNER_SALAD_RULE = CategoryRule(ItemCategory.SALAD, 3, {"uk": "Салати", "ru": "Салаты", "en": "Salads"})
DRINK_RULE = CategoryRule(ItemCategory.DRINK, 4, {"uk": "Напої", "ru": "Напитки", "en": "Drinks"})

MEAL_RULES = {
    MEAL_BREAKFAST: (MAIN_RULE, BREAKFAST_SWEET_RULE, DRINK_RULE),
    MEAL_DINNER: (MAIN_RULE, DINNER_SALAD_RULE, DRINK_RULE),
}

STYLE_LABELS = {
    "black_silk_robe": {"uk": "Чорний шовковий халат із мереживом", "ru": "Чёрный шёлковый халат с кружевом", "en": "Black silk lace robe"},
    "beige_silk_robe": {"uk": "Бежевий шовковий халат із мереживом", "ru": "Бежевый шёлковый халат с кружевом", "en": "Beige silk lace robe"},
    "mens_white_shirt": {"uk": "Чоловіча біла сорочка", "ru": "Мужская белая рубашка", "en": "Men's white shirt"},
    "corset": {"uk": "Корсет", "ru": "Корсет", "en": "Corset"},
    "with_partner": {"uk": "Разом зі своїм чоловіком", "ru": "Со своим мужчиной", "en": "Together with my partner"},
}


def meal_rules(meal_period: str | None) -> tuple[CategoryRule, ...]:
    return MEAL_RULES.get(str(meal_period), MEAL_RULES[MEAL_DINNER])


def category_rule(meal_period: str | None, category: ItemCategory | str) -> CategoryRule:
    value = ItemCategory(category) if isinstance(category, str) else category
    for rule in meal_rules(meal_period):
        if rule.category == value:
            return rule
    raise ValueError("Category is not available for the selected meal")


def style_label(style: str | None, language: str = "ru") -> str:
    labels = STYLE_LABELS.get(str(style), {})
    return labels.get(language, labels.get("ru", str(style or "—")))


def meal_label(meal_period: str | None, language: str = "ru") -> str:
    labels = {
        MEAL_BREAKFAST: {"uk": "Сніданок", "ru": "Завтрак", "en": "Breakfast"},
        MEAL_DINNER: {"uk": "Вечеря", "ru": "Ужин", "en": "Dinner"},
    }
    selected = labels.get(str(meal_period), labels[MEAL_DINNER])
    return selected.get(language, selected["ru"])


def normalize_dish_lines(text: str, *, limit: int, language: str = "ru") -> list[str]:
    raw_lines = [line for line in text.splitlines() if line.strip()]
    if len(raw_lines) == 1 and raw_lines[0].strip().casefold() in SKIP_WORDS:
        return []
    titles: list[str] = []
    seen: set[str] = set()
    for raw in raw_lines:
        value = re.sub(r"^\s*(?:[-*•·]+|\d+[.)])\s*", "", raw.strip())
        value = re.sub(r"\s+", " ", value).strip(" ,;–—")
        if not value or value.casefold() in SKIP_WORDS:
            continue
        if not any(char.isalnum() for char in value):
            value = SURPRISE_TITLES.get(language, SURPRISE_TITLES["ru"])
        if len(value) > 180:
            raise ValueError("Dish title must contain no more than 180 characters")
        if value.casefold() not in seen:
            seen.add(value.casefold())
            titles.append(value)
    if len(titles) > limit:
        raise ValueError(f"Category accepts no more than {limit} dishes")
    return titles
