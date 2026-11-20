"""Release-candidate owner dashboard: no provider, payment or database needed."""
from datetime import UTC, datetime, timedelta

import pytest

from app.little_legend.owner_production_dashboard import build_dashboard


NOW = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)


def row(quote_id, status, *, age=5, lease=None, started=None, delivered=None):
    return (
        quote_id, status, NOW - timedelta(minutes=age),
        lease, started, delivered,
    )


def test_empty_dashboard_has_no_attention():
    result = build_dashboard([], now=NOW)
    assert result.total_orders == 0
    assert result.attention_required == 0
    assert not result.automatic_retry_allowed


def test_stale_order_visible_without_child_data():
    result = build_dashboard([row(1, "processing")], now=NOW)
    assert result.attention_required == 1
    assert result.orders[0].alerts == ["stale_pdf_lease"]
    assert "story_id" not in result.model_dump_json()
    assert "owner_id" not in result.model_dump_json()


def test_healthy_live_lease_is_not_alerted():
    result = build_dashboard([
        row(2, "processing", lease=NOW + timedelta(minutes=1)),
    ], now=NOW)
    assert result.attention_required == 0


def test_unconfirmed_telegram_is_not_retried():
    result = build_dashboard([
        row(3, "ready", started=NOW - timedelta(minutes=1)),
    ], now=NOW)
    assert result.orders[0].alerts == ["delivery_unconfirmed"]
    assert not result.automatic_retry_allowed


def test_counts_and_pagination():
    rows = [row(1, "ready"), row(2, "blocked"), row(3, "pending")]
    result = build_dashboard(rows, now=NOW, limit=2)
    assert result.total_orders == 2
    assert result.has_more
    assert result.by_status == {"ready": 1, "blocked": 1}
    assert result.attention_required == 1


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_invalid_limit_rejected(limit):
    with pytest.raises(ValueError, match="limit"):
        build_dashboard([], now=NOW, limit=limit)


def test_timezone_required():
    with pytest.raises(ValueError, match="Timezone"):
        build_dashboard([], now=datetime(2026, 11, 20))
