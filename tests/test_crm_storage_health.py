"""Storage dashboard health: distinguish inaccessible R2 from empty buckets."""
from datetime import UTC, datetime
from unittest.mock import Mock, patch

from app.crm.r2_storage import inventory


def test_unconfigured_r2_has_explicit_status_not_zero_usage():
    result = inventory(env={})
    assert result["status"] == "not_configured"
    assert result["total_used_bytes"] is None
    assert result["providers"] == []


def test_r2_permission_failure_is_visible_without_leaking_credentials():
    target = {"provider": "illustrations", "bucket": "private"}
    client = Mock()
    client.list_objects_v2.side_effect = PermissionError("secret access key")
    with (
        patch("app.crm.r2_storage.configured_targets", return_value=[target]),
        patch("app.crm.r2_storage.client_for", return_value=client),
    ):
        result = inventory()
    assert result["status"] == "partial"
    assert result["total_used_bytes"] is None
    assert result["providers"][0]["status"] == "error"
    assert result["providers"][0]["used_bytes"] is None
    assert "secret access key" not in str(result)


def test_successful_empty_bucket_is_real_zero():
    target = {"provider": "release", "bucket": "private"}
    client = Mock()
    client.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
    with (
        patch("app.crm.r2_storage.configured_targets", return_value=[target]),
        patch("app.crm.r2_storage.client_for", return_value=client),
    ):
        result = inventory()
    assert result["status"] == "ok"
    assert result["total_used_bytes"] == 0
    assert result["providers"][0]["bot_id"] == "little_legend"


def test_partial_listing_never_claims_exact_total():
    target = {"provider": "release", "bucket": "private"}
    client = Mock()
    client.list_objects_v2.return_value = {
        "Contents": [{
            "Key": "little-legend/releases/a.pdf", "Size": 10,
            "LastModified": datetime(2026, 11, 21, tzinfo=UTC),
        }] * 5000,
        "IsTruncated": True,
    }
    with (
        patch("app.crm.r2_storage.configured_targets", return_value=[target]),
        patch("app.crm.r2_storage.client_for", return_value=client),
    ):
        result = inventory()
    assert result["providers"][0]["status"] == "partial"
    assert result["total_used_bytes"] is None
