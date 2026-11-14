"""Never delete paid-order assets during disk cleanup."""
import os
import time

import pytest

from app.services.gift_cleanup import cleanup_scratch


def test_dry_run_and_delete_only_expired_scratch(tmp_path):
    root = tmp_path / "storage"
    scratch = root / "cache" / "gift_scratch"
    scratch.mkdir(parents=True)
    old = scratch / "old.tmp"
    fresh = scratch / "new.tmp"
    old.write_bytes(b"old")
    fresh.write_bytes(b"new")
    now = time.time()
    os.utime(old, (now - 100000, now - 100000))
    paid = root / "generated" / "wallpapers" / "paid.png"
    paid.parent.mkdir(parents=True)
    paid.write_bytes(b"customer")
    result = cleanup_scratch(root, now=now)
    assert result.deleted == 1
    assert old.exists()
    result = cleanup_scratch(root, now=now, dry_run=False)
    assert result.deleted == 1
    assert result.reclaimed_bytes == 3
    assert not old.exists()
    assert fresh.exists()
    assert paid.read_bytes() == b"customer"


def test_short_retention_rejected(tmp_path):
    with pytest.raises(ValueError, match="six hours"):
        cleanup_scratch(tmp_path, max_age_hours=1)


def test_symlink_not_followed(tmp_path):
    root = tmp_path / "storage"
    scratch = root / "cache" / "gift_scratch"
    scratch.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep")
    link = scratch / "outside"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unsupported")
    result = cleanup_scratch(root, dry_run=False)
    assert result.deleted == 0
    assert outside.read_bytes() == b"keep"
