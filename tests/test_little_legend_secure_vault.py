"""Fail-closed vault foundation tests. No child photos or media fixtures."""
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.little_legend.secure_vault import (
    AssetState,
    MediaEnvelope,
    authorize_asset,
    deletion_failed,
    deletion_succeeded,
    new_asset_metadata,
    request_deletion,
    retention_expired,
    upload_capability,
)


def test_no_upload_capability():
    status = upload_capability()
    assert status["enabled"] is False
    assert status["storage_backend_connected"] is False
    assert status["automatic_cleanup_running"] is False


def test_metadata_owner_isolation_and_private_keys():
    asset = new_asset_metadata(owner_id=123, story_id=456)
    assert asset.object_key.startswith("little-legend/private/")
    assert "123" not in asset.object_key
    authorize_asset(asset, owner_id=123, story_id=456)
    with pytest.raises(PermissionError):
        authorize_asset(asset, owner_id=999, story_id=456)
    with pytest.raises(PermissionError):
        authorize_asset(asset, owner_id=123, story_id=999)


def test_limits_and_retention():
    MediaEnvelope(content_type="image/jpeg", byte_size=100, width=100, height=100)
    with pytest.raises(ValidationError):
        MediaEnvelope(content_type="image/jpeg", byte_size=13_000_000, width=100, height=100)
    with pytest.raises(ValidationError):
        MediaEnvelope(content_type="image/png", byte_size=100, width=8000, height=8000)
    with pytest.raises(ValidationError):
        MediaEnvelope(content_type="application/pdf", byte_size=100, width=100, height=100)
    with pytest.raises(ValueError):
        new_asset_metadata(owner_id=1, story_id=2, retention_days=31)


def test_deletion_is_explicit_and_idempotent():
    now = datetime.now(UTC)
    asset = new_asset_metadata(owner_id=1, story_id=2, now=now)
    assert not retention_expired(asset, now=now)
    assert retention_expired(asset, now=now + timedelta(days=8))
    pending = request_deletion(asset)
    assert pending.state == AssetState.DELETION_PENDING
    failed = deletion_failed(pending, error_code="OBJECT_STORE_TIMEOUT")
    assert failed.state == AssetState.DELETE_FAILED
    assert failed.deletion_attempts == 1
    pending_again = request_deletion(failed)
    deleted = deletion_succeeded(pending_again, now=now)
    assert deleted.state == AssetState.DELETED
    assert deleted.deleted_at == now
    assert request_deletion(deleted).state == AssetState.DELETED
    assert asset.state == AssetState.RESERVED
    with pytest.raises(ValueError):
        deletion_succeeded(asset)


def test_vault_status_route_exists():
    from app.little_legend.router import router

    assert any(
        route.path.endswith("/api/stories/{story_id}/photo-vault")
        and "GET" in route.methods
        for route in router.routes
    )
