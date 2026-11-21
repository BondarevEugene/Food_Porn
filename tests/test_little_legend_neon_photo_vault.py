"""Photo metadata schema and authorization are independent of public routes."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.little_legend.neon_photo_vault import photo_assets
from app.little_legend.secure_vault import (
    AssetState,
    authorize_asset,
    new_asset_metadata,
)


def test_photo_metadata_contains_no_image_or_prompt_columns():
    columns = {column.name for column in photo_assets.columns}
    assert {"asset_id", "owner_id", "story_id", "object_key", "state", "expires_at"} <= columns
    assert not columns.intersection({"image", "image_bytes", "photo", "prompt", "public_url"})
    sql = str(CreateTable(photo_assets).compile(dialect=postgresql.dialect()))
    assert "little_legend_photo_assets" in sql


def test_new_private_asset_is_opaque_reserved_and_expires():
    now = datetime.now(UTC)
    asset = new_asset_metadata(owner_id=5, story_id=7, now=now)
    assert asset.state == AssetState.RESERVED
    assert asset.expires_at == now + timedelta(days=7)
    assert asset.object_key == "little-legend/private/" + asset.asset_id
    assert len(asset.asset_id) == 48
    authorize_asset(asset, owner_id=5, story_id=7)
    with pytest.raises(PermissionError):
        authorize_asset(asset, owner_id=6, story_id=7)
