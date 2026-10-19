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
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.database.models import ItemCategory

MEAL_BREAKFAST = "breakfast"
MEAL_DINNER = "dinner"
MEAL_FULL_DAY = "full_day"
DEFAULT_VISUAL_STYLE = "premium_dark"

SLOT_BREAKFAST = "breakfast"
SLOT_LUNCH = "lunch"
SLOT_DINNER = "dinner"
SLOT_OTHER = "other"

SKIP_WORDS = frozenset({"пас", "pass", "skip", "пропустить", "пропустити", "-", "—"})
SURPRISE_TITLES = {"uk": "Сюрприз від шефа", "ru": "Сюрприз от повара", "en": "Chef's surprise"}


@dataclass(frozen=True, slots=True)
class CategoryRule:
    category: ItemCategory
    limit: int
    labels: dict[str, str]

    def label(self, language: str) -> str:
        return self.labels.get(language, self.labels["ru"])


@dataclass(frozen=True, slots=True)
class MenuPlanEntry:
    meal_slot: str
    title: str
    category: ItemCategory


MAIN_RULE = CategoryRule(ItemCategory.MAIN, 9, {"uk": "Основні страви", "ru": "Основные блюда", "en": "Main dishes"})
BREAKFAST_SWEET_RULE = CategoryRule(ItemCategory.DESSERT, 3, {"uk": "Солодкі сніданки", "ru": "Сладкие завтраки", "en": "Sweet breakfasts"})
DINNER_SALAD_RULE = CategoryRule(ItemCategory.SALAD, 3, {"uk": "Салати", "ru": "Салаты", "en": "Salads"})
DRINK_RULE = CategoryRule(ItemCategory.DRINK, 4, {"uk": "Напої", "ru": "Напитки", "en": "Drinks"})

MEAL_RULES = {
    MEAL_BREAKFAST: (MAIN_RULE, BREAKFAST_SWEET_RULE, DRINK_RULE),
    MEAL_DINNER: (MAIN_RULE, DINNER_SALAD_RULE, DRINK_RULE),
}

STYLE_LABELS = {
    DEFAULT_VISUAL_STYLE: {"uk": "Преміальний темний стиль", "ru": "Премиальный тёмный стиль", "en": "Premium dark style"},
    "black_silk_robe": {"uk": "Чорний шовковий халат із мереживом", "ru": "Чёрный шёлковый халат с кружевом", "en": "Black silk lace robe"},
    "beige_silk_robe": {"uk": "Бежевий шовковий халат із мереживом", "ru": "Бежевый шёлковый халат с кружевом", "en": "Beige silk lace robe"},
    "mens_white_shirt": {"uk": "Чоловіча біла сорочка", "ru": "Мужская белая рубашка", "en": "Men's white shirt"},
    "corset": {"uk": "Корсет", "ru": "Корсет", "en": "Corset"},
    "with_partner": {"uk": "Разом зі своїм чоловіком", "ru": "Со своим мужчиной", "en": "Together with my partner"},
}

MEAL_SLOT_LABELS = {
    SLOT_BREAKFAST: {"uk": "Сніданок", "ru": "Завтрак", "en": "Breakfast"},
    SLOT_LUNCH: {"uk": "Обід", "ru": "Обед", "en": "Lunch"},
    SLOT_DINNER: {"uk": "Вечеря", "ru": "Ужин", "en": "Dinner"},
    SLOT_OTHER: {"uk": "Інше", "ru": "Без раздела", "en": "Other"},
}

CYRILLIC_TO_LATIN = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "ґ": "g", "д": "d", "е": "e", "ё": "e",
    "є": "ye", "ж": "zh", "з": "z", "и": "i", "і": "i", "ї": "yi", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})

# Canonical Latin spelling lets one matcher understand Cyrillic, transliteration,
# diacritics, and mixed-language input without an extra OpenAI request.
MEAL_HEADING_ALIASES = {
    SLOT_BREAKFAST: frozenset({
        "zavtrak", "snidanok", "breakfast", "desayuno", "petit dejeuner",
        "fruhstuck", "colazione", "sniadanie", "cafe da manha", "ontbijt",
    }),
    SLOT_LUNCH: frozenset({
        "obed", "obid", "lunch", "almuerzo", "dejeuner", "mittagessen",
        "pranzo", "obiad", "almoco", "middageten",
    }),
    SLOT_DINNER: frozenset({
        "uzhin", "vecherya", "vecheria", "dinner", "cena", "diner",
        "abendessen", "kolacja", "jantar", "avondeten", "souper",
    }),
}

DRINK_TERMS = frozenset({
    "voda", "water", "eau", "wasser", "agua", "acqua", "kofe", "kava",
    "coffee", "cafe", "caffe", "kaffee", "tea", "chai", "chay", "vino", "wine",
    "wino", "wein", "vin", "sok", "sik", "juice", "jus", "limonad",
    "lemonade", "kompot", "beer", "pivo", "cerveza", "birra", "bier",
})
DESSERT_TERMS = frozenset({
    "desert", "dessert", "tort", "cake", "kuchen", "pastel", "tiramisu",
    "ice cream", "gelato", "helado",
})
DESSERT_STEMS = frozenset({"morozhen", "tistech", "pirog"})
SALAD_TERMS = frozenset({"salat", "salad", "ensalada", "insalata"})
SOUP_TERMS = frozenset({"sup", "soup", "soupe", "sopa", "zuppa", "uha"})
SOUP_STEMS = frozenset({"borshch", "borsch", "yushk"})


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
        MEAL_FULL_DAY: {"uk": "Меню на день", "ru": "Меню на день", "en": "Daily menu"},
    }
    selected = labels.get(str(meal_period), labels[MEAL_DINNER])
    return selected.get(language, selected["ru"])


def meal_slot_label(meal_slot: str | None, language: str = "ru") -> str:
    labels = MEAL_SLOT_LABELS.get(str(meal_slot), MEAL_SLOT_LABELS[SLOT_OTHER])
    return labels.get(language, labels["ru"])


def _normalize_words(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    transliterated = without_accents.translate(CYRILLIC_TO_LATIN)
    return re.sub(r"[^a-z0-9]+", " ", transliterated).strip()


def _contains_term(value: str, terms: frozenset[str], stems: frozenset[str] = frozenset()) -> bool:
    padded = f" {value} "
    if any(f" {term} " in padded for term in terms):
        return True
    return any(token.startswith(stem) for token in value.split() for stem in stems)


def infer_item_category(title: str) -> ItemCategory:
    normalized = _normalize_words(title)
    if _contains_term(normalized, DRINK_TERMS):
        return ItemCategory.DRINK
    if _contains_term(normalized, DESSERT_TERMS, DESSERT_STEMS):
        return ItemCategory.DESSERT
    if _contains_term(normalized, SALAD_TERMS):
        return ItemCategory.SALAD
    if _contains_term(normalized, SOUP_TERMS, SOUP_STEMS):
        return ItemCategory.SOUP
    return ItemCategory.MAIN


def _without_list_marker(value: str) -> str:
    return re.sub(r"^\s*(?:[-*•·▪▫]+|\d+[.)])\s*", "", value.strip())


def _meal_heading(value: str) -> str | None:
    normalized = _normalize_words(_without_list_marker(value))
    if not normalized or len(normalized.split()) > 3:
        return None
    for meal_slot, aliases in MEAL_HEADING_ALIASES.items():
        if normalized in aliases:
            return meal_slot
    # Fuzzy matching is deliberately conservative: very short words require an
    # exact match, and large length differences are rejected. This recognizes
    # "завтрк" / "breakfest" without turning dish names into headings.
    if len(normalized) < 5:
        return None
    for meal_slot, aliases in MEAL_HEADING_ALIASES.items():
        for alias in aliases:
            if abs(len(normalized) - len(alias)) > max(2, len(alias) // 4):
                continue
            cutoff = 0.84 if len(alias) <= 6 else 0.78
            if SequenceMatcher(None, normalized, alias).ratio() >= cutoff:
                return meal_slot
    return None


def parse_menu_plan(
    text: str,
    *,
    language: str = "ru",
    max_items: int = 18,
) -> list[MenuPlanEntry]:
    """Parse one multiline message; meal headings are separators, never dishes."""
    current_slot = SLOT_OTHER
    entries: list[MenuPlanEntry] = []
    seen: set[tuple[str, str]] = set()
    for raw in text.splitlines():
        if not raw.strip():
            continue
        heading = _meal_heading(raw)
        if heading:
            current_slot = heading
            continue
        value = re.sub(r"\s+", " ", _without_list_marker(raw)).strip(" ,;–—")
        if not value or value.casefold() in SKIP_WORDS:
            continue
        if not any(char.isalnum() for char in value):
            value = SURPRISE_TITLES.get(language, SURPRISE_TITLES["ru"])
        if len(value) > 180:
            raise ValueError("Dish title must contain no more than 180 characters")
        key = (current_slot, value.casefold())
        if key in seen:
            continue
        seen.add(key)
        entries.append(MenuPlanEntry(current_slot, value, infer_item_category(value)))
    if not entries:
        raise ValueError("Menu must contain at least one dish")
    if len(entries) > max_items:
        raise ValueError(f"Menu accepts no more than {max_items} dishes")
    return entries


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
