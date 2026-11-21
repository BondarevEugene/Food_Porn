"""Mini CRM operational safety contracts for the owner dashboard."""
from pathlib import Path

JS = Path("app/crm/static/crm.js")


def test_dashboard_expenses_are_labeled_uah():
    source = JS.read_text(encoding="utf-8")
    assert "num(month.expenses_total_uah||0)+'<span class=\"unit\">UAH</span>'" in source
    assert "num(month.expenses_total_uah||0)+'<span class=\"unit\">Stars</span>'" not in source


def test_storage_reconciliation_is_visible_but_not_deletable():
    source = JS.read_text(encoding="utf-8")
    assert "get('/storage/r2/reconcile')" in source
    assert "reconcilePanel+bookSection" in source
    assert "Удаление файлов запрещено" in source
    assert "findings_truncated" in source


def test_three_product_pricing_groups_keep_existing_settings_keys():
    source = JS.read_text(encoding="utf-8")
    for product in ("Food_Porn", "Меню для любимого", "Little Legend"):
        assert product in source
    for key in (
        "gift_price_stars", "menu_price_uah", "menu_price_stars",
        "little_legend_digital_price_uah", "little_legend_print_price_uah",
        "price_electronic_uah", "price_print_uah",
    ):
        assert key in source
    assert "Группировка цен не меняет принадлежность существующих заказов" in source
