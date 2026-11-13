"""Premium menu: world cuisines, print-ready labels, and document output."""
from pathlib import Path

import pytest
from PIL import Image

from app.database.models import ItemCategory
from app.render.recipes import render_recipe_sheet
from app.services.cuisine_catalog import CUISINES, cuisine_menu
from app.services.menu_wizard import (
    category_label,
    display_dish_title,
    meal_slot_label,
)


@pytest.mark.parametrize("lang", ["uk", "ru", "en"])
def test_eight_world_cuisines_propose_editable_balanced_menus(lang):
    assert len(CUISINES) == 8
    for cuisine in CUISINES:
        plan = cuisine_menu(cuisine.code, lang)
        assert len(plan) == 6
        assert len({item.title for item in plan}) == len(plan)
        assert all(item.title and item.category for item in plan)
        assert any(item.category == ItemCategory.MAIN for item in plan)
        assert any(item.category == ItemCategory.DRINK for item in plan)
        assert any(item.category == ItemCategory.DESSERT for item in plan)


def test_cuisine_can_omit_drink_or_dessert_before_order_generation():
    plan = cuisine_menu("italian", "ru", drinks=False, dessert=False)
    assert plan
    assert all(
        item.category not in {ItemCategory.DRINK, ItemCategory.DESSERT}
        for item in plan
    )
    with pytest.raises(ValueError, match="Unknown world cuisine"):
        cuisine_menu("imaginary")


def test_printed_title_avoids_internal_labels_and_repairs_known_typo():
    assert display_dish_title("КОтлета по киевски") == "Котлета по-киевски"
    assert display_dish_title("вареники") == "Вареники"
    assert meal_slot_label("other", "ru") != "Без раздела"
    assert category_label(ItemCategory.SOUP, "ru") == "Супы"


def test_recipe_book_renders_with_dish_photo_and_checklist(tmp_path: Path):
    photo = tmp_path / "food.jpg"
    Image.new("RGB", (150, 180), (160, 70, 40)).save(photo)
    result = render_recipe_sheet(
        tmp_path / "premium.pdf",
        {"борщ": {
            "ingredients": ["Свёкла — 200 г", "Мясо — 300 г"],
            "recipe": "1. Подготовьте овощи.\n2. Варите бульон.",
            "difficulty": "medium", "servings": 2,
        }},
        ["• Свёкла: 200 г"],
        "ru", meal_plan=[("other", "борщ")],
        dish_images={"борщ": str(photo)},
    )
    assert result.read_bytes().startswith(b"%PDF")
    assert result.stat().st_size > 5000
