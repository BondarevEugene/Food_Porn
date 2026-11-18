"""Regression checks for Little Legend Telegram Mini App links."""
from app.bot.handlers.little_legend import little_legend_studio_url


def test_studio_url_from_railway_origin():
    assert little_legend_studio_url("https://food.example.com") == (
        "https://food.example.com/little-legend"
    )


def test_studio_url_from_existing_miniapp_path():
    assert little_legend_studio_url("https://food.example.com/miniapp/") == (
        "https://food.example.com/little-legend"
    )


def test_studio_url_rejects_unsafe_configuration():
    for value in ("", "http://food.example.com", "https://user:pass@food.example.com"):
        assert little_legend_studio_url(value) is None
