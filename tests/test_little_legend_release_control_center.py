"""Release Control Center is a read-only, mobile-friendly authenticated shell."""

import pytest

from app.little_legend.release_control_center import RELEASE_CONTROL_HTML
from app.little_legend.router import release_control_center


@pytest.mark.asyncio
async def test_release_control_route_serves_no_store_html():
    response = await release_control_center()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert b"Release Control" in response.body


def test_dashboard_uses_telegram_authorization_for_every_private_request():
    assert "window.Telegram?.WebApp?.initData" in RELEASE_CONTROL_HTML
    assert "Authorization:'tma '+auth" in RELEASE_CONTROL_HTML
    assert "if(!auth)" in RELEASE_CONTROL_HTML


def test_dashboard_does_not_expose_mutating_payment_or_generation_actions():
    assert "/order-quotes/'+id+'/status" in RELEASE_CONTROL_HTML
    assert "/order-quotes/'+id+'/diagnostics" in RELEASE_CONTROL_HTML
    assert "/order-quotes/'+id+'/book.pdf" in RELEASE_CONTROL_HTML
    assert "/checkout" not in RELEASE_CONTROL_HTML
    # The only permitted mutation repairs a previously confirmed delivery
    # projection; it must never initiate payment, generation or Telegram send.
    assert RELEASE_CONTROL_HTML.count("method:'POST'") == 1
    assert "/stories/'+id+'/delivery-reconcile" in RELEASE_CONTROL_HTML
    assert "x.action==='repair_projection'" in RELEASE_CONTROL_HTML
    assert "Number.isSafeInteger(x.telegram_message_id)" in RELEASE_CONTROL_HTML
    assert "recoverableStory!==id||!auth" in RELEASE_CONTROL_HTML
    assert "method:'PUT'" not in RELEASE_CONTROL_HTML
    assert "/regenerate" not in RELEASE_CONTROL_HTML
    assert "/retry" not in RELEASE_CONTROL_HTML


def test_mobile_and_accessibility_controls_exist():
    assert "@media(max-width:650px)" in RELEASE_CONTROL_HTML
    assert 'aria-live="polite"' in RELEASE_CONTROL_HTML
    assert 'id="refresh"' in RELEASE_CONTROL_HTML
    assert 'id="download"' in RELEASE_CONTROL_HTML


def test_error_text_is_inserted_as_text_not_html():
    assert "title.textContent=label(code)" in RELEASE_CONTROL_HTML
    assert "detail.textContent='Код: '+code" in RELEASE_CONTROL_HTML
    assert "innerHTML" not in RELEASE_CONTROL_HTML
