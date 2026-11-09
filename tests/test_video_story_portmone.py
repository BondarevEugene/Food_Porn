"""Portmone має окремий простір ідентифікаторів для відеоісторій."""

import pytest

from app.services.payment import PAYMENT_PRODUCTS, PaymentService


def test_video_story_portmone_reference_is_separate():
    assert "video_story" in PAYMENT_PRODUCTS
    assert PaymentService._order_number(12, "video_story") == "video_story_12"
    assert PaymentService._order_number(12, "wallpaper") == "wallpaper_12"


def test_portmone_rejects_unknown_product():
    with pytest.raises(ValueError):
        PaymentService._order_number(12, "unknown")
