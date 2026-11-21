"""R2 console: bounded inventory, configuration and destructive-action guards."""
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from app.crm.r2_storage import configured_targets, delete_selected, inventory


def test_targets_only_include_complete_private_connections():
    env = {
        "LITTLE_LEGEND_ART_S3_ENDPOINT": "https://r2.example.com",
        "LITTLE_LEGEND_ART_S3_BUCKET": "private",
        "LITTLE_LEGEND_ART_S3_REGION": "auto",
        "LITTLE_LEGEND_ART_S3_ACCESS_KEY": "key",
        "LITTLE_LEGEND_ART_S3_SECRET_KEY": "secret",
    }
    targets = configured_targets(env)
    assert len(targets) == 1
    assert targets[0]["provider"] == "illustrations"


def test_inventory_summarizes_real_objects_and_ignores_diagnostics():
    target = {"provider": "illustrations", "bucket": "private"}
    client = Mock()
    client.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "little-legend/generated/a.jpg", "Size": 512,
             "LastModified": datetime(2026, 11, 21, tzinfo=UTC), "ETag": '"etag"'},
            {"Key": "little-legend/diagnostics/test.bin", "Size": 96,
             "LastModified": datetime(2026, 11, 21, tzinfo=UTC)},
        ],
        "IsTruncated": False,
    }
    with (
        patch("app.crm.r2_storage.configured_targets", return_value=[target]),
        patch("app.crm.r2_storage.client_for", return_value=client),
    ):
        result = inventory()
    assert result["total_used_bytes"] == 512
    assert result["providers"][0]["object_count"] == 1
    assert result["providers"][0]["free_bytes"] is None


@pytest.mark.parametrize("keys", [
    [], ["outside/file.jpg"], ["little-legend/diagnostics/test.bin"],
    ["little-legend/../secret"], ["little-legend/a"] * 2,
])
def test_deletion_rejects_unsafe_or_duplicate_selection(keys):
    with pytest.raises(HTTPException):
        delete_selected(provider="illustrations", keys=keys, env={})


def test_deletion_requires_explicit_configured_provider():
    with pytest.raises(HTTPException) as exc:
        delete_selected(provider="illustrations", keys=["little-legend/generated/a.jpg"], env={})
    assert exc.value.status_code == 404
