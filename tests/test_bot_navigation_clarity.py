"""Client navigation keeps product choices separate from service actions."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import wallpaper
from app.bot.handlers.start import get_products_menu_keyboard
from app.bot.handlers.wallpaper import (
    gift_keyboard,
    gift_photo_start_keyboard,
    gift_product_keyboard,
    gift_review_keyboard,
)
from app.bot.states.wallpaper import WallpaperStates
from app.config import Settings


def _actions(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_main_menu_contains_two_products_and_orders_before_services():
    actions = _actions(get_products_menu_keyboard(user_id=123, lang="uk"))
    assert actions[:4] == [
        "prod_food_porn", "prod_manifestation", "home_orders", "home_services"
    ]
    assert not any(action in actions for action in (
        "home_instruction", "home_faq", "home_support",
        "home_referral", "choose_language",
    ))


def test_main_menu_admin_entry_is_separate():
    actions = _actions(get_products_menu_keyboard(user_id=123, lang="en", is_admin=True))
    assert actions[:4] == [
        "prod_food_porn", "prod_manifestation", "home_orders", "home_services"
    ]
    assert actions[-1] == "admin_home"


def test_gift_style_does_not_offer_to_restart_photo_upload():
    actions = _actions(gift_keyboard("ru", "light"))
    assert actions == [
        "gift_style:dark", "gift_style:light", "gift_style:color",
        "gift_back_to_product", "back_to_products",
    ]
    assert "gift_five_photos" not in actions


def test_gift_product_choices_are_distinct_from_service_buttons():
    actions = _actions(gift_product_keyboard("uk"))
    assert actions == [
        "gift_product:collage", "gift_product:video", "gift_product:both",
        "gift_back_to_photos", "back_to_products",
    ]


def test_initial_photo_screen_has_no_styles_or_service_actions():
    assert _actions(gift_photo_start_keyboard("en")) == [
        "gift_five_photos", "back_to_products",
    ]


def test_order_review_has_one_primary_decision_and_edit_path():
    assert _actions(gift_review_keyboard("ru")) == [
        "gift_review_confirm", "gift_review_edit", "back_to_products",
    ]


@pytest.mark.asyncio
async def test_stale_review_buttons_do_not_change_current_order():
    callback = SimpleNamespace(
        answer=AsyncMock(), from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(answer=AsyncMock()),
    )
    state = SimpleNamespace(get_state=AsyncMock(return_value=WallpaperStates.waiting_for_product.state))
    await wallpaper.edit_gift_review(callback, state)
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs["show_alert"] is True
    callback.message.answer.assert_not_awaited()
    callback.answer.reset_mock()
    await wallpaper.confirm_gift_review(
        callback, state, Settings(_env_file=None, gift_unified_checkout_enabled=True),
        None,
    )
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs["show_alert"] is True
    callback.message.answer.assert_not_awaited()


def test_order_review_is_localized_and_escapes_customer_goals():
    quote = SimpleNamespace(
        product_choice="both", visual_style="light",
        goals=["House <sea>", "Trip"] ,
        collage_amount=10, video_amount=20, total_amount=30,
    )
    message = wallpaper.gift_review_text("ru", quote, photo_count=2)
    assert "Шаг 4/4" in message
    assert "Коллаж + видео" in message
    assert "House &lt;sea&gt;" in message
    assert "🌙 Тёмный" not in message
    assert "☀️ Светлый" in message
    assert "<b>Итого: 30.00 UAH</b>" in message
