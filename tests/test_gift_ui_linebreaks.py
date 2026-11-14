"""Regression checks for Telegram gift screen line breaks."""
from decimal import Decimal
from types import SimpleNamespace

from app.bot.handlers.wallpaper import gift_review_text


def test_gift_review_uses_real_newlines_not_literal_escape_sequences():
    quote = SimpleNamespace(
        product_choice="both",
        visual_style="light",
        goals=["Дом у моря", "Подорож", "Родина", "Здоров'я", "Успіх"],
        collage_amount=Decimal("100"),
        video_amount=Decimal("200"),
        total_amount=Decimal("300"),
    )
    for language in ("uk", "ru", "en"):
        rendered = gift_review_text(language, quote, photo_count=3)
        assert "\\n" not in rendered
        assert rendered.count("\n") >= 10
        assert "300.00 UAH" in rendered
        assert "3" in rendered
