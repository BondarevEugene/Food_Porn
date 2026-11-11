"""Mini App must not display a misleading empty order list after HTTP 401."""
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "app/miniapp/static/app.js").read_text(encoding="utf-8")


def test_http_401_has_distinct_auth_failure_status():
    assert "if (response.status === 401)" in SOURCE
    assert "error.status = 401;" in SOURCE


def test_failed_auth_hides_empty_orders_and_provides_retry():
    assert "function authFailureView()" in SOURCE
    assert "state.home = null;\n        authFailureView();" in SOURCE
    assert "Your orders have not been deleted." in SOURCE
    assert "if (action === 'retry-auth') { await open('home'); return; }" in SOURCE


def test_unloaded_home_does_not_claim_zero_orders():
    assert "if (!state.home) return '—';" in SOURCE
