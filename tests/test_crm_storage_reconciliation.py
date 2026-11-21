"""Storage reconciliation cannot promote unknown files to deletion candidates."""
from app.crm.storage_reconciliation import reconcile


def provider(status="ok", objects=None):
    return {
        "bot_id": "little_legend", "provider": "release",
        "bucket": "private", "status": status, "truncated": False,
        "objects": objects or [],
    }


def test_unknown_objects_remain_protected():
    report = reconcile(
        {"providers": [provider(objects=[{"key": "unknown.pdf", "bytes": 42}])]},
        [],
    )
    assert report["status"] == "complete"
    assert report["counts"]["unregistered"] == 1
    assert report["findings"][0]["protected"] is True
    assert report["deletion_enabled"] is False


def test_partial_inventory_cannot_claim_registered_object_missing():
    registered = [{
        "bot_id": "little_legend", "connection": "release",
        "bucket": "private", "object_key": "book.pdf",
        "bytes": 100, "etag": None, "state": "protected",
    }]
    report = reconcile({"providers": [provider(status="error")]}, registered)
    assert report["status"] == "partial"
    assert "missing_in_r2" not in report["counts"]


def test_complete_inventory_detects_missing_and_size_mismatch():
    registered = [{
        "bot_id": "little_legend", "connection": "release",
        "bucket": "private", "object_key": "book.pdf",
        "bytes": 100, "etag": None, "state": "protected",
    }]
    report = reconcile(
        {"providers": [provider(objects=[{"key": "book.pdf", "bytes": 20}])]},
        registered,
    )
    assert report["counts"]["size_mismatch"] == 1
    assert report["findings"][0]["protected"] is True


def test_shared_bucket_does_not_duplicate_registered_illustration():
    row = {
        "bot_id": "little_legend", "connection": "illustrations",
        "bucket": "private", "object_key": "little-legend/generated/a.jpg",
        "bytes": 42, "etag": None, "state": "protected",
    }
    shared = provider(objects=[{"key": row["object_key"], "bytes": 42}])
    shared["prefix"] = "little-legend/"
    report = reconcile({"providers": [shared, dict(shared)]}, [row])
    assert report["counts"] == {"registered": 1}
    assert report["findings"] == []


def test_unrelated_prefix_does_not_prove_missing_object():
    row = {
        "bot_id": "little_legend", "connection": "release",
        "bucket": "private", "object_key": "little-legend/releases/book.pdf",
        "bytes": 100, "etag": None, "state": "protected",
    }
    limited = provider()
    limited["prefix"] = "little-legend/generated/"
    report = reconcile({"providers": [limited]}, [row])
    assert report["status"] == "complete"
    assert "missing_in_r2" not in report["counts"]
