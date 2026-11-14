"""Regression tests for the Telegram-only progressive menu interface."""
from types import SimpleNamespace

from app.bot.handlers.menu import MenuAction, build_dashboard_kb, format_premium_dashboard
from app.database.models import MenuStatus


def _menu(*, dishes=0, cover=False, spread=False):
    return SimpleNamespace(
        id=21, meal_period="full_day", status=MenuStatus.DRAFT,
        customer=SimpleNamespace(language="ru"), is_paid=False,
        items=[SimpleNamespace(title=f"Dish {i}") for i in range(dishes)],
        cover_photo_path="cover.jpg" if cover else None,
        spread_photo_path="spread.jpg" if spread else None,
    )


def _actions(menu):
    result = []
    for row in build_dashboard_kb(menu).inline_keyboard:
        for button in row:
            value = button.callback_data or ""
            if value.startswith("menu:"):
                result.append(value)
            else:
                result.append(value)
    return result


def test_menu_lux_has_one_primary_action_per_step():
    for menu, action in [
        (_menu(), "menu_dish_methods"),
        (_menu(dishes=2), "req_cover"),
        (_menu(dishes=2, cover=True), "req_spread"),
        (_menu(dishes=2, cover=True, spread=True), "generate"),
    ]:
        buttons = build_dashboard_kb(menu).inline_keyboard
        assert len(buttons) <= 4
        assert len(buttons[0]) == 1
        assert action in buttons[0][0].callback_data
        assert "menu_more" in buttons[1][0].callback_data


def test_menu_lux_progress_is_readable_and_has_real_newlines():
    text = format_premium_dashboard(_menu(dishes=2, cover=True))
    assert "Готовность: 2/3" in text
    assert "Фото разворота" in text
    assert "\\n" not in text
    assert "\n" in text


def test_menu_lux_uses_existing_menu_action_contract():
    callback = MenuAction(action="menu_dish_methods", menu_id=21).pack()
    assert MenuAction.unpack(callback).menu_id == 21
