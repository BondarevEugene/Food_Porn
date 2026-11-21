"""Preflight audit must not persist customer object names or allow deletion."""
from app.crm.storage_audit import ACTION, summarize_check


def test_preflight_audit_is_non_destructive_and_redacted():
    details = summarize_check(
        bot_id="little_legend", provider="release",
        keys=["little-legend/private/customer-name.pdf"],
        outcome="protected", total_bytes=123, secret="test-secret",
    )
    assert ACTION == "storage.preflight"
    assert details["destructive"] is False
    assert details["total_bytes"] == 123
    assert details["count"] == 1
    assert "customer-name" not in str(details)
    assert len(details["fingerprints"][0]) == 64


def test_preflight_fingerprints_are_stable_and_keyed():
    args = {
        "bot_id": "little_legend", "provider": "release",
        "keys": ["secret/file.pdf"], "outcome": "protected",
    }
    a = summarize_check(**args, secret="first")
    b = summarize_check(**args, secret="first")
    c = summarize_check(**args, secret="second")
    assert a["fingerprints"] == b["fingerprints"]
    assert a["fingerprints"] != c["fingerprints"]
