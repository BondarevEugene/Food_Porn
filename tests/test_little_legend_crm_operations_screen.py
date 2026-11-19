"""Regression guards for the Little Legend CRM production screen."""
from pathlib import Path

from app.crm.router import little_legend_paid_production

STATIC = Path(__file__).resolve().parents[1] / "app" / "crm" / "static"


def test_crm_production_api_is_present():
    assert little_legend_paid_production.__name__ == "little_legend_paid_production"


def test_legend_console_loads_both_queues():
    source = (STATIC / "crm.js").read_text(encoding="utf-8")
    assert "Promise.all([get('/little-legend/delivery-queue')" in source
    assert "get('/little-legend/paid-production?limit=100')" in source
    assert "possibly_stalled_render" in source
    assert "telegram_delivery_requires_reconciliation" in source
    assert "data-action=\"legend-detail\"" in source


def test_crm_assets_cache_busted():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "crm-legend-operations-20261119" in html
    assert "Little Legend · производство" in html


def test_crm_legend_responsive():
    css = (STATIC / "crm.css").read_text(encoding="utf-8")
    assert ".legend-metrics" in css
    assert ".legend-table-scroll" in css
