"""S3 adapter boundary tests; no network calls."""
from datetime import UTC, datetime

import pytest

from app.little_legend.image_safety import SanitizedImage
from app.little_legend.object_store import (
    S3Settings,
    _validate_key,
    store_sanitized_photo,
)
from app.little_legend.secure_vault import new_asset_metadata


class FakeStore:
    def __init__(self):
        self.writes = []

    def put(self, *, key, data, content_type):
        self.writes.append((key, data, content_type))

    def delete(self, *, key):
        pass


def test_https_required():
    with pytest.raises(ValueError):
        S3Settings("http://example.test", "bucket", "region", "id", "secret")


def test_key_is_private_and_randomized():
    asset = new_asset_metadata(owner_id=1, story_id=2, now=datetime.now(UTC))
    _validate_key(asset.object_key)
    for key in ("other/abc", "little-legend/private/../../secret",
                "little-legend/private/" + "x" * 48):
        with pytest.raises(ValueError):
            _validate_key(key)


def test_consent_and_ownership_are_required():
    asset = new_asset_metadata(owner_id=1, story_id=2, now=datetime.now(UTC))
    image = SanitizedImage(b"jpeg", "image/jpeg", 1, 1)
    store = FakeStore()
    with pytest.raises(PermissionError):
        store_sanitized_photo(
            store, asset=asset, owner_id=1, story_id=2, image=image
        )
    with pytest.raises(PermissionError):
        store_sanitized_photo(
            store, asset=asset, owner_id=99, story_id=2, image=image,
            consent_verified=True,
        )
    assert not store.writes
    store_sanitized_photo(
        store, asset=asset, owner_id=1, story_id=2, image=image,
        consent_verified=True,
    )
    assert store.writes == [(asset.object_key, b"jpeg", "image/jpeg")]
