"""Little Legend checkout is always quote-backed and fail-closed."""
import pytest

from app.services.wayforpay import PRODUCTS, WayForPayError, WayForPayService


def test_little_legend_is_registered_payment_product():
    assert "little_legend" in PRODUCTS


def test_little_legend_cannot_use_a_global_fallback_price():
    service = object.__new__(WayForPayService)
    with pytest.raises(WayForPayError, match="immutable database quote"):
        service.price_for("little_legend")


def test_unrecognized_products_remain_rejected():
    assert "little_legend_print" not in PRODUCTS
