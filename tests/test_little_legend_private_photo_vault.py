"""Private vault integration contract: ownership, expiry, consent, object existence."""
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image

from app.little_legend.private_photo_vault import AuthorizedPrivatePhotoVault
from app.little_legend.secure_vault import AssetState


class Metadata:
    def __init__(self):
        self.assets = {}

    async def get_asset(self, *, asset_id):
        return self.assets.get(asset_id)

    async def create_asset(self, *, asset):
        self.assets[asset.asset_id] = asset

    async def mark_stored(self, *, asset_id):
        self.assets[asset_id] = self.assets[asset_id].model_copy(
            update={"state": AssetState.STORED},
        )


class Objects:
    def __init__(self):
        self.data = {}

    def put(self, *, key, data):
        self.data[key] = data

    def get(self, *, key):
        return self.data[key]

    def delete(self, *, key):
        del self.data[key]


def _image():
    output = BytesIO()
    Image.new("RGB", (80, 80)).save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_consent_required_before_any_storage():
    metadata, objects = Metadata(), Objects()
    vault = AuthorizedPrivatePhotoVault(metadata=metadata, objects=objects)
    with pytest.raises(PermissionError, match="consent"):
        await vault.upload_private_photo(
            owner_id=1, story_id=2, data=_image(), consent_confirmed=False,
        )
    assert not metadata.assets
    assert not objects.data


@pytest.mark.asyncio
async def test_owner_scoped_upload_preflight_and_read():
    metadata, objects = Metadata(), Objects()
    vault = AuthorizedPrivatePhotoVault(metadata=metadata, objects=objects)
    asset = await vault.upload_private_photo(
        owner_id=1, story_id=2, data=_image(), consent_confirmed=True,
    )
    assert asset.state == AssetState.STORED
    await vault.check_access(
        owner_id=1, story_id=2, reference_ids={asset.asset_id},
    )
    result = await vault.read_reference(
        owner_id=1, story_id=2, reference_id=asset.asset_id,
    )
    assert result.startswith(bytes((255, 216, 255)))
    with pytest.raises(PermissionError, match="not found"):
        await vault.read_reference(
            owner_id=3, story_id=2, reference_id=asset.asset_id,
        )
    with pytest.raises(PermissionError, match="not found"):
        await vault.read_reference(
            owner_id=1, story_id=4, reference_id=asset.asset_id,
        )


@pytest.mark.asyncio
async def test_expired_asset_and_deleted_object_block_worker():
    metadata, objects = Metadata(), Objects()
    vault = AuthorizedPrivatePhotoVault(metadata=metadata, objects=objects)
    asset = await vault.upload_private_photo(
        owner_id=1, story_id=2, data=_image(), consent_confirmed=True,
    )
    objects.delete(key=asset.object_key)
    with pytest.raises(KeyError):
        await vault.check_access(
            owner_id=1, story_id=2, reference_ids={asset.asset_id},
        )
    metadata.assets[asset.asset_id] = asset.model_copy(
        update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)},
    )
    with pytest.raises(PermissionError, match="not found"):
        await vault.read_reference(
            owner_id=1, story_id=2, reference_id=asset.asset_id,
        )
