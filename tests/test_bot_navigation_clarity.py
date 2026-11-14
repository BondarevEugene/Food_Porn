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
        "gift_review_confirm", "gift_review_edit", "gift_review_change_product", "back_to_products",
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


@pytest.mark.asyncio
async def test_change_product_from_review_preserves_draft_and_invalidates_quote():
    draft = {
        "lang": "ru", "gift_product": "both", "gift_quote_id": "old-quote",
        "goals": ["Дом у моря"] * 5, "style": "light", "photos": ["photo-1"],
    }
    callback = SimpleNamespace(
        answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()),
    )
    state = SimpleNamespace(
        get_state=AsyncMock(return_value=WallpaperStates.waiting_for_confirmation.state),
        get_data=AsyncMock(return_value=draft.copy()),
        update_data=AsyncMock(), set_state=AsyncMock(),
    )
    await wallpaper.change_gift_product_from_review(callback, state)
    state.update_data.assert_awaited_once_with(gift_quote_id=None)
    state.set_state.assert_awaited_once_with(WallpaperStates.waiting_for_product)
    markup = callback.message.answer.await_args.kwargs["reply_markup"]
    selected = [b.text for row in markup.inline_keyboard for b in row if b.callback_data == "gift_product:both"]
    assert len(selected) == 1 and selected[0].startswith("✓ ")
    assert draft["goals"] == ["Дом у моря"] * 5
    assert draft["photos"] == ["photo-1"]


@pytest.mark.asyncio
async def test_change_product_rejects_stale_review():
    callback = SimpleNamespace(
        answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()),
    )
    state = SimpleNamespace(get_state=AsyncMock(return_value=WallpaperStates.waiting_for_product.state))
    await wallpaper.change_gift_product_from_review(callback, state)
    assert callback.answer.await_args.kwargs["show_alert"] is True
    callback.message.answer.assert_not_awaited()


def test_saved_goals_keyboard_keeps_primary_action_first():
    actions = _actions(wallpaper.gift_saved_goals_keyboard("ru", "light"))
    assert actions[0] == "gift_goals_continue"
    assert actions[1:4] == ["gift_style:dark", "gift_style:light", "gift_style:color"]
    assert actions[-1] == "back_to_products"


@pytest.mark.asyncio
async def test_saved_goals_continue_rejects_missing_goals():
    callback = SimpleNamespace(answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))
    state = SimpleNamespace(
        get_state=AsyncMock(return_value=WallpaperStates.waiting_for_goals.state),
        get_data=AsyncMock(return_value={"lang": "ru", "goals": []}),
    )
    await wallpaper.continue_saved_gift_goals(callback, state, Settings(_env_file=None), None)
    assert callback.answer.await_args.kwargs["show_alert"] is True
    callback.message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_saved_goals_continue_uses_customer_identity(monkeypatch):
    goals = ["Мечта " + str(i) for i in range(5)]
    customer = SimpleNamespace(id=91)
    original = SimpleNamespace(model_copy=lambda update: SimpleNamespace(**update))
    callback = SimpleNamespace(answer=AsyncMock(), message=original, from_user=customer)
    state = SimpleNamespace(
        get_state=AsyncMock(return_value=WallpaperStates.waiting_for_goals.state),
        get_data=AsyncMock(return_value={"lang": "ru", "goals": goals}),
    )
    collect = AsyncMock()
    monkeypatch.setattr(wallpaper, "collect_goals", collect)
    await wallpaper.continue_saved_gift_goals(callback, state, Settings(_env_file=None), None)
    assert collect.await_count == 1
    message = collect.await_args.args[0]
    assert message.from_user is customer
    assert message.text == "\\n".join(goals)


def test_gift_progress_shows_independent_deliveries_without_fake_percentage():
    purchase = SimpleNamespace(status="paid", includes_collage=True, includes_video=True)
    job = SimpleNamespace(status="processing", collage_sent=True, video_sent=False)
    text = wallpaper.gift_progress_text("ru", purchase, job)
    assert "Коллаж: доставлен" in text
    assert "Видео: ожидается" in text
    assert "%" not in text


def test_gift_progress_video_only_never_exposes_internal_collage():
    purchase = SimpleNamespace(status="paid", includes_collage=False, includes_video=True)
    job = SimpleNamespace(status="processing", collage_sent=False, video_sent=False)
    text = wallpaper.gift_progress_text("en", purchase, job)
    assert "Collage" not in text
    assert "Video: pending" in text


def test_gift_progress_keyboard_has_one_refresh_action():
    purchase_id = "f2db361c-5e12-4c91-aec9-b1d8d7f01a33"
    assert _actions(wallpaper.gift_progress_keyboard("ru", purchase_id)) == [
        "gift_status:" + purchase_id
    ]


@pytest.mark.asyncio
async def test_gift_progress_rejects_invalid_purchase_id():
    callback = SimpleNamespace(data="gift_status:not-a-uuid", answer=AsyncMock())
    await wallpaper.show_paid_gift_status(callback, None, None)
    assert callback.answer.await_args.kwargs["show_alert"] is True
