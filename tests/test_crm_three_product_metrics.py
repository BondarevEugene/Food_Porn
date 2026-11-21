"""Contract checks for the three-product Mini CRM operations dashboard."""
from pathlib import Path


def test_product_metrics_use_separate_payment_and_creation_dates():
    service = Path("app/crm/service.py").read_text(encoding="utf-8")
    start = service.index("async def product_metrics(")
    end = service.index("async def dashboard(", start)
    code = service[start:end]
    assert "orders.c.created_at >= begin" in code
    assert "orders.c.paid_at >= begin" in code
    assert 'orders.c.payment_kind == "cash"' in code
    assert 'orders.c.payment_kind == "stars"' in code
    assert '"little_legend_included": False' in code
    assert '"consolidated_finance": False' in code


def test_dashboard_shows_three_sources_without_fabricated_book_revenue():
    js = Path("app/crm/static/crm.js").read_text(encoding="utf-8")
    assert "get('/product-metrics?days='+state.days)" in js
    assert "get('/little-legend/paid-production?limit=100')" in js
    assert "Финансовые данные не подключены" in js
    assert "UAH и Stars учитываются раздельно" in js


def test_product_metrics_route_requires_identity():
    router = Path("app/crm/router.py").read_text(encoding="utf-8")
    assert '@router.get("/api/product-metrics")' in router
    assert "async def product_metrics(identity: Identity, days: Days = 30)" in router
