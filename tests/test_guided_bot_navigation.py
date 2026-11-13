"""Customer-facing UI must show the current step, not every possible action."""
from __future__ import annotations

from types import SimpleNamespace

from app.bot.handlers.menu import build_dashboard_kb, build_menu_options_kb, format_premium_dashboard
from app.bot.handlers.start import get_products_menu_keyboard, get_services_keyboard
from app.bot.handlers.wallpaper import gift_goals_keyboard, gift_keyboard, gift_product_keyboard
from app.database.models import MenuStatus


def callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_home_only_has_two_products_and_separate_services():
    assert callbacks(get_products_menu_keyboard(lang="ru")) == [
        "prod_food_porn", "prod_manifestation", "home_services",
    ]
    services = callbacks(get_services_keyboard(lang="ru"))
    assert "home_orders" in services and "home_support" in services
    assert "admin_home" not in services


def test_gift_photo_format_goals_are_distinct_screens():
    photos = callbacks(gift_keyboard("ru"))
    products = callbacks(gift_product_keyboard("ru"))
    goals = callbacks(gift_goals_keyboard("ru", "light"))
    assert photos == ["gift_five_photos", "back_to_products"]
    assert products == ["gift_product:collage", "gift_product:video", "gift_product:both"]
    assert "gift_five_photos" not in goals
    assert "gift_back_to_product" in goals
    assert len([button for button in goals if button.startswith("gift_style:")]) == 3
    assert gift_goals_keyboard("ru", "light").inline_keyboard[0][1].text.startswith("✓ ")


def test_menu_dashboard_recommends_only_the_next_missing_step():
    menu = SimpleNamespace(
        id=72, status=MenuStatus.DRAFT,
        items=[], cover_photo_path=None, spread_photo_path=None,
    )
    first = callbacks(build_dashboard_kb(menu))
    assert any("pick_category" in value for value in first)
    assert any("bulk_items" in value for value in first)
    assert not any("generate" in value or "req_cover" in value for value in first)

    menu.items = [SimpleNamespace(title="Salad", meal_slot="lunch")]
    second = callbacks(build_dashboard_kb(menu))
    assert any("req_cover" in value for value in second)
    assert not any("req_spread" in value or "generate" in value for value in second)

    menu.cover_photo_path = "cover.png"
    third = callbacks(build_dashboard_kb(menu))
    assert any("req_spread" in value for value in third)
    assert not any("generate" in value for value in third)

    menu.spread_photo_path = "spread.png"
    fourth = callbacks(build_dashboard_kb(menu))
    assert any("generate" in value for value in fourth)
    assert not any("req_cover" in value for value in fourth)

    extras = callbacks(build_menu_options_kb(menu))
    assert any("choose_cuisine" in value for value in extras)
    assert any("view" in value for value in extras)


def test_menu_dashboard_explains_current_step():
    menu = SimpleNamespace(
        id=10, status=MenuStatus.DRAFT,
        items=[], cover_photo_path=None, spread_photo_path=None,
        meal_period="full_day",
    )
    assert "Сейчас: добавьте блюда" in format_premium_dashboard(menu)
