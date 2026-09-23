"""
==========================================================
FOOD_PORN

Module: Menu Plan Tests
Layer: Test

Responsibilities:
    - Verify the twelve-position category plan
    - Verify skip-word normalization
==========================================================
"""

from app.bot.helpers import ITEM_PLAN
from app.database.models import ItemCategory
from app.database.repositories import is_skipped_title


def test_menu_plan_has_twelve_items_across_four_categories() -> None:
    assert sum(count for _, count, _ in ITEM_PLAN) == 12
    assert [category for category, _, _ in ITEM_PLAN] == [
        ItemCategory.MAIN,
        ItemCategory.APPETIZER,
        ItemCategory.DESSERT,
        ItemCategory.DRINK,
    ]


def test_pass_word_is_recognized_by_repository_contract() -> None:
    assert is_skipped_title("пас") is True
    assert is_skipped_title(" ПАС ") is True
    assert is_skipped_title("pass") is True
    assert is_skipped_title("Тирамису") is False
