"""Regression tests for combined gift review and price validation."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.bot.handlers.wallpaper import gift_review_keyboard, gift_review_text
from app.services.gift_purchases import quote_amounts

GOALS = ["Дом у моря", "Путешествия", "Семья", "Здоровье", "Свобода"]


@pytest.mark.parametrize("lang", ["uk", "ru", "en"])
def test_both_light_five_goals_review(lang):
    quote = SimpleNamespace(
        product_choice="both",
        visual_style="light",
        goals=GOALS,
        collage_amount=Decimal("120.00"),
        video_amount=Decimal("280.00"),
        total_amount=Decimal("400.00"),
    )
    text = gift_review_text(lang, quote, photo_count=3)
    assert "120.00 UAH" in text
    assert "280.00 UAH" in text
    assert "400.00 UAH" in text
    assert all(goal in text for goal in GOALS)
    assert "\\n" not in text
    assert text.count("\n") >= 10
    callbacks = [
        button.callback_data
        for row in gift_review_keyboard(lang).inline_keyboard
        for button in row
    ]
    assert callbacks == ["gift_review_confirm", "gift_review_edit", "gift_review_change_product", "back_to_products"]


def test_both_quote_adds_prices_without_rounding_or_hidden_fees():
    assert quote_amounts(
        "both", collage_price=Decimal("120.00"),
        video_price=Decimal("280.00"),
    ) == (Decimal("120.00"), Decimal("280.00"), Decimal("400.00"))


@pytest.mark.parametrize("video_price", [None, Decimal("0"), Decimal("-1")])
def test_both_checkout_rejects_unconfigured_video_price(video_price):
    with pytest.raises(ValueError):
        quote_amounts(
            "both", collage_price=Decimal("120.00"),
            video_price=video_price,
        )
