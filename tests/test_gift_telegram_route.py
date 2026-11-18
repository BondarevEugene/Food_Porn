"""The gift journey stays in Telegram and exposes one clear step at a time."""

import pytest

from app.bot.handlers.wallpaper import gift_product_keyboard, gift_route_header


@pytest.mark.parametrize("lang", ["uk", "ru", "en"])
def test_gift_route_header_localized_and_four_step_progress(lang):
    for step in range(1, 5):
        title = gift_route_header(lang, step, "Фото", "Фотографии", "Photos")
        assert f"{step}/4" in title
        assert title.count("●") == step
        assert title.count("○") == 4 - step
        assert "\n" in title
        assert "\\n" not in title


def test_gift_route_header_rejects_invalid_step():
    with pytest.raises(ValueError):
        gift_route_header("ru", 5, "Фото", "Фото", "Photos")


def test_gift_format_keyboard_has_all_choices_and_back_to_photos():
    buttons = [button for row in gift_product_keyboard("ru", "both").inline_keyboard for button in row]
    callbacks = [button.callback_data for button in buttons]
    assert callbacks[:3] == ["gift_product:collage", "gift_product:video", "gift_product:both"]
    assert callbacks[3] == "gift_back_to_photos"
    assert "✓" in buttons[2].text
    assert all(button.web_app is None for button in buttons)
