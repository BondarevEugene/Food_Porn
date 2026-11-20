"""Recovery Center never retries uncertain Telegram sends or paid work."""

from app.little_legend.release_control_center import RELEASE_CONTROL_HTML


def test_recovery_has_distinct_story_id_input():
    assert 'id="recoveryStory"' in RELEASE_CONTROL_HTML
    assert 'id="quote"' in RELEASE_CONTROL_HTML
    assert "Number($('recoveryStory').value)" in RELEASE_CONTROL_HTML


def test_recovery_starts_as_read_only():
    assert "/stories/'+id+'/delivery-diagnosis" in RELEASE_CONTROL_HTML
    assert 'id="repairProjection" type="button" disabled' in RELEASE_CONTROL_HTML
    assert "recoverableStory=null" in RELEASE_CONTROL_HTML


def test_repair_requires_confirmed_provider_message_id():
    assert "x.action==='repair_projection'" in RELEASE_CONTROL_HTML
    assert "Number.isSafeInteger(x.telegram_message_id)" in RELEASE_CONTROL_HTML
    assert "x.telegram_message_id>0" in RELEASE_CONTROL_HTML
    assert "recoverableStory!==id||!auth" in RELEASE_CONTROL_HTML


def test_repair_calls_only_existing_reconciliation_api():
    assert "/stories/'+id+'/delivery-reconcile" in RELEASE_CONTROL_HTML
    assert "method:'POST'" in RELEASE_CONTROL_HTML
    assert "/checkout" not in RELEASE_CONTROL_HTML
    assert "/retry" not in RELEASE_CONTROL_HTML
    assert "/regenerate" not in RELEASE_CONTROL_HTML


def test_ambiguous_delivery_is_never_auto_retried():
    assert "x.action==='manual_review'" in RELEASE_CONTROL_HTML
    assert "Автоматический повтор запрещён" in RELEASE_CONTROL_HTML
    assert "window.confirm(" in RELEASE_CONTROL_HTML


def test_recovery_uses_telegram_auth_and_safe_dom_updates():
    assert "Authorization:'tma '+auth" in RELEASE_CONTROL_HTML
    assert "$('recoveryMessage').textContent" in RELEASE_CONTROL_HTML
    assert "innerHTML" not in RELEASE_CONTROL_HTML
