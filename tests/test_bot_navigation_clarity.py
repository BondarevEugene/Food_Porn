"""Client navigation keeps product choices separate from service actions."""
from app.bot.handlers.start import get_products_menu_keyboard
from app.bot.handlers.wallpaper import gift_keyboard, gift_product_keyboard


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
        "back_to_products",
    ]
    assert "gift_five_photos" not in actions


def test_gift_product_choices_are_distinct_from_service_buttons():
    actions = _actions(gift_product_keyboard("uk"))
    assert actions == [
        "gift_product:collage", "gift_product:video", "gift_product:both"
    ]
