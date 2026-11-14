"""Pre-payment storage health and operator verification checks."""
from pathlib import Path

import pytest

from app.services.gift_storage import GiftStorageUnavailable, require_gift_storage


def test_verified_writable_absolute_storage(tmp_path):
    require_gift_storage(tmp_path, operator_verified=True)
    assert list(tmp_path.iterdir()) == []


def test_unverified_storage_blocks_checkout(tmp_path):
    with pytest.raises(GiftStorageUnavailable, match="not been verified"):
        require_gift_storage(tmp_path, operator_verified=False)


def test_relative_storage_blocks_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("storage").mkdir()
    with pytest.raises(GiftStorageUnavailable, match="absolute"):
        require_gift_storage(Path("storage"), operator_verified=True)


def test_missing_storage_blocks_checkout(tmp_path):
    with pytest.raises(GiftStorageUnavailable, match="existing"):
        require_gift_storage(tmp_path / "missing", operator_verified=True)


def test_symlink_storage_blocks_checkout(tmp_path):
    link = tmp_path / "linked"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this platform")
    with pytest.raises(GiftStorageUnavailable, match="symlink"):
        require_gift_storage(link, operator_verified=True)
