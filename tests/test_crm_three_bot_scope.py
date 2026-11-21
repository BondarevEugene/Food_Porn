"""Prevent misleading three-bot consolidation claims in Mini CRM."""
from pathlib import Path


def test_three_bot_coverage_is_explicit_and_read_only():
    router = Path("app/crm/router.py").read_text(encoding="utf-8")
    assert '@router.get("/api/product-scope")' in router
    assert '"id": "food_porn"' in router
    assert '"id": "menu_for_loved_one"' in router
    assert '"id": "little_legend"' in router
    assert '"orders_in_common_feed": False' in router
    assert '"consolidated_finance": False' in router


def test_dashboard_discloses_nonconsolidated_finance():
    js = Path("app/crm/static/crm.js").read_text(encoding="utf-8")
    assert "get('/product-scope')" in js
    assert "scopeNotice(data.productScope)" in js
    assert "Общая финансовая сводка пока не объединяет все три бота" in js
