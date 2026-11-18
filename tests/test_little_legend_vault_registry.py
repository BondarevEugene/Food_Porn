"""Vault registry is private metadata, never an upload capability."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.little_legend.secure_vault import AssetState, new_asset_metadata
from app.little_legend.vault_registry import (
    metadata,
    request_expired_deletions,
    vault_assets,
)


def test_registry_schema_and_private_metadata():
    assert vault_assets.name == "little_legend_vault_assets"
    assert {"owner_id", "story_id", "expires_at", "state"}.issubset(
        vault_assets.c.keys()
    )
    assert "image_data" not in vault_assets.c
    assert "photo_bytes" not in vault_assets.c
    assert "face_embedding" not in vault_assets.c
    assert any(index.name == "ix_ll_vault_owner_story" for index in vault_assets.indexes)
    assert vault_assets.metadata is metadata


def test_vault_retention_is_bounded():
    now = datetime.now(UTC)
    asset = new_asset_metadata(owner_id=1, story_id=2, now=now)
    assert asset.state == AssetState.RESERVED
    assert asset.expires_at == now + timedelta(days=7)


@pytest.mark.asyncio
async def test_expiry_queue_rejects_invalid_batch_without_db():
    with pytest.raises(ValueError):
        await request_expired_deletions(None, batch_size=0)


def test_registry_query_is_not_public_media_endpoint():
    from app.little_legend.router import router

    paths = {route.path for route in router.routes}
    assert "/little-legend/api/stories/{story_id}/vault-summary" in paths
    assert not any(path.endswith("/upload") for path in paths)
    assert select(vault_assets.c.asset_id) is not None
