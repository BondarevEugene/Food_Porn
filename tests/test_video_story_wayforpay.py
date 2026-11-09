"""Перевірки окремої ціни та платіжного типу відеоісторії."""

from decimal import Decimal

import pytest

from app.config import Settings
from app.services.wayforpay import PRODUCTS, WayForPayError, WayForPayService


def test_video_story_is_separate_wayforpay_product():
    assert {"menu", "wallpaper", "video_story"} <= PRODUCTS


def test_video_story_price_is_fail_closed_until_configured():
    settings = Settings()
    settings.wayforpay_video_story_price_uah = None
    with pytest.raises(WayForPayError, match="price is not configured"):
        WayForPayService(settings).price_for("video_story")


def test_video_story_has_independent_price():
    settings = Settings()
    settings.wayforpay_video_story_price_uah = Decimal("149.00")
    assert WayForPayService(settings).price_for("video_story") == Decimal("149.00")
