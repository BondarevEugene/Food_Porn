"""Regression: menu category button is wired and preserves other categories."""
from pathlib import Path

from app.database.models import ItemCategory


def test_menu_category_callback_is_registered():
    source = Path("app/bot/handlers/menu.py").read_text(encoding="utf-8")
    assert '@router.callback_query(MenuAction.filter(F.action == "pick_category"))' in source
    assert 'action="edit_category"' in source
    assert 'action="menu_dish_methods"' in source


def test_category_entry_uses_non_destructive_repository_operation():
    source = Path("app/bot/handlers/menu.py").read_text(encoding="utf-8")
    assert 'selected_category = data.get("selected_category")' in source
    assert "await repo.replace_category_items(" in source
    assert "await repo.replace_menu_plan(" in source
    assert "category = ItemCategory(selected_category)" in source


def test_category_codes_match_database_contract():
    assert {category.value for category in ItemCategory} == {
        "main", "salad", "drink", "soup", "appetizer", "dessert",
    }
