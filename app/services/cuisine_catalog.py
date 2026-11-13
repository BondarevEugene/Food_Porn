"""Curated cuisine menus for the premium Food_Porn dinner wizard.

These are suggested menus, not medically tailored meal plans. Every proposal
can be edited in the existing manual dish editor before paid generation.
No OpenAI API call (or charge) is made by choosing a cuisine.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.database.models import ItemCategory
from app.services.menu_wizard import SLOT_DINNER, MenuPlanEntry


@dataclass(frozen=True, slots=True)
class Cuisine:
    code: str
    labels: tuple[str, str, str]
    dishes: tuple[tuple[ItemCategory, str, str, str], ...]

    def label(self, lang: str) -> str:
        return self.labels[{"uk": 0, "ru": 1, "en": 2}.get(lang, 1)]

    def plan(self, lang: str) -> list[MenuPlanEntry]:
        index = {"uk": 1, "ru": 2, "en": 3}.get(lang, 2)
        return [
            MenuPlanEntry(SLOT_DINNER, dish[index], dish[0])
            for dish in self.dishes
        ]


CUISINES: tuple[Cuisine, ...] = (
    Cuisine("ukrainian", ("🇺🇦 Українська", "🇺🇦 Украинская", "🇺🇦 Ukrainian"), (
        (ItemCategory.SALAD, "Салат зі свіжих овочів", "Салат из свежих овощей", "Fresh vegetable salad"),
        (ItemCategory.SOUP, "Борщ український", "Украинский борщ", "Ukrainian borscht"),
        (ItemCategory.MAIN, "Котлета по-київськи", "Котлета по-киевски", "Chicken Kyiv"),
        (ItemCategory.APPETIZER, "Деруни зі сметаною", "Драники со сметаной", "Potato pancakes with sour cream"),
        (ItemCategory.DRINK, "Узвар", "Узвар", "Uzvar fruit drink"),
        (ItemCategory.DESSERT, "Сирники з ягодами", "Сырники с ягодами", "Syrnyky with berries"),
    )),
    Cuisine("italian", ("🇮🇹 Італійська", "🇮🇹 Итальянская", "🇮🇹 Italian"), (
        (ItemCategory.APPETIZER, "Брускета з томатами", "Брускетта с томатами", "Tomato bruschetta"),
        (ItemCategory.SALAD, "Капрезе", "Капрезе", "Caprese salad"),
        (ItemCategory.MAIN, "Паста з грибами", "Паста с грибами", "Mushroom pasta"),
        (ItemCategory.MAIN, "Курка по-тосканськи", "Курица по-тоскански", "Tuscan chicken"),
        (ItemCategory.DRINK, "Домашній лимонад", "Домашний лимонад", "Homemade lemonade"),
        (ItemCategory.DESSERT, "Тирамісу", "Тирамису", "Tiramisu"),
    )),
    Cuisine("french", ("🇫🇷 Французька", "🇫🇷 Французская", "🇫🇷 French"), (
        (ItemCategory.APPETIZER, "Кіш із сиром", "Киш с сыром", "Cheese quiche"),
        (ItemCategory.SOUP, "Цибулевий суп", "Луковый суп", "French onion soup"),
        (ItemCategory.MAIN, "Курка в вершковому соусі", "Курица в сливочном соусе", "Chicken in cream sauce"),
        (ItemCategory.SALAD, "Салат із гірчичною заправкою", "Салат с горчичной заправкой", "Mustard vinaigrette salad"),
        (ItemCategory.DRINK, "Лимонад із травами", "Лимонад с травами", "Herbal lemonade"),
        (ItemCategory.DESSERT, "Крем-брюле", "Крем-брюле", "Crème brûlée"),
    )),
    Cuisine("georgian", ("🇬🇪 Грузинська", "🇬🇪 Грузинская", "🇬🇪 Georgian"), (
        (ItemCategory.APPETIZER, "Пхалі зі шпинату", "Пхали из шпината", "Spinach pkhali"),
        (ItemCategory.SALAD, "Овочевий салат із горіхами", "Овощной салат с орехами", "Vegetable walnut salad"),
        (ItemCategory.MAIN, "Чахохбілі", "Чахохбили", "Chakhokhbili chicken stew"),
        (ItemCategory.APPETIZER, "Хачапурі по-аджарськи", "Хачапури по-аджарски", "Adjarian khachapuri"),
        (ItemCategory.DRINK, "Тархун", "Тархун", "Tarragon lemonade"),
        (ItemCategory.DESSERT, "Пеламуші", "Пеламуши", "Pelamushi grape dessert"),
    )),
    Cuisine("japanese", ("🇯🇵 Японська", "🇯🇵 Японская", "🇯🇵 Japanese"), (
        (ItemCategory.APPETIZER, "Едамаме", "Эдамаме", "Edamame"),
        (ItemCategory.SOUP, "Місо-суп", "Мисо-суп", "Miso soup"),
        (ItemCategory.MAIN, "Курка теріякі з рисом", "Курица терияки с рисом", "Teriyaki chicken with rice"),
        (ItemCategory.SALAD, "Салат із огірків", "Салат из огурцов", "Japanese cucumber salad"),
        (ItemCategory.DRINK, "Зелений чай", "Зелёный чай", "Green tea"),
        (ItemCategory.DESSERT, "Моті", "Моти", "Mochi"),
    )),
    Cuisine("mexican", ("🇲🇽 Мексиканська", "🇲🇽 Мексиканская", "🇲🇽 Mexican"), (
        (ItemCategory.APPETIZER, "Гуакамоле з начос", "Гуакамоле с начос", "Guacamole and nachos"),
        (ItemCategory.SALAD, "Салат із кукурудзи", "Салат из кукурузы", "Mexican corn salad"),
        (ItemCategory.MAIN, "Курячі фахітас", "Куриные фахитас", "Chicken fajitas"),
        (ItemCategory.MAIN, "Кесадилья із сиром", "Кесадилья с сыром", "Cheese quesadilla"),
        (ItemCategory.DRINK, "Лаймова вода", "Лаймовая вода", "Lime agua fresca"),
        (ItemCategory.DESSERT, "Чурос", "Чуррос", "Churros"),
    )),
    Cuisine("mediterranean", ("🌿 Середземноморська", "🌿 Средиземноморская", "🌿 Mediterranean"), (
        (ItemCategory.APPETIZER, "Хумус", "Хумус", "Hummus"),
        (ItemCategory.SALAD, "Грецький салат", "Греческий салат", "Greek salad"),
        (ItemCategory.MAIN, "Запечена риба з лимоном", "Запечённая рыба с лимоном", "Lemon baked fish"),
        (ItemCategory.APPETIZER, "Овочі на грилі", "Овощи на гриле", "Grilled vegetables"),
        (ItemCategory.DRINK, "Лимонад із м'ятою", "Лимонад с мятой", "Mint lemonade"),
        (ItemCategory.DESSERT, "Йогурт із медом і горіхами", "Йогурт с мёдом и орехами", "Yogurt with honey and nuts"),
    )),
    Cuisine("american", ("🇺🇸 Американська", "🇺🇸 Американская", "🇺🇸 American"), (
        (ItemCategory.APPETIZER, "Кукурудза на грилі", "Кукуруза на гриле", "Grilled corn"),
        (ItemCategory.SALAD, "Коул-слоу", "Коул-слоу", "Coleslaw"),
        (ItemCategory.MAIN, "Домашній бургер", "Домашний бургер", "Homemade burger"),
        (ItemCategory.APPETIZER, "Картопля по-селянськи", "Картофель по-деревенски", "Country-style potato wedges"),
        (ItemCategory.DRINK, "Ягідний морс", "Ягодный морс", "Berry fruit drink"),
        (ItemCategory.DESSERT, "Брауні", "Брауни", "Brownies"),
    )),
)
CUISINE_BY_CODE = {c.code: c for c in CUISINES}


def cuisine_menu(code: str, language: str = "ru", *, drinks: bool = True,
                 dessert: bool = True) -> list[MenuPlanEntry]:
    """Deterministic, editable proposal; no surprises or billable AI calls."""
    cuisine = CUISINE_BY_CODE.get(code)
    if cuisine is None:
        raise ValueError("Unknown world cuisine")
    entries = cuisine.plan(language)
    return [
        entry for entry in entries
        if (drinks or entry.category != ItemCategory.DRINK)
        and (dessert or entry.category != ItemCategory.DESSERT)
    ]
