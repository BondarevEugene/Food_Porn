"""Fail-closed storage preflight before taking payment for generated gifts.

A successful write test establishes current filesystem health, NOT durability
across Railway redeployments. The operator must verify the mounted volume.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path


class GiftStorageUnavailable(RuntimeError):
    """Do not accept a paid gift when its files cannot be retained."""


def require_gift_storage(root: Path, *, operator_verified: bool) -> None:
    """Require explicit volume verification and a writable storage directory."""
    root = Path(root)
    if not operator_verified:
        raise GiftStorageUnavailable("Persistent gift storage has not been verified")
    if not root.is_absolute() or not root.is_dir():
        raise GiftStorageUnavailable("Gift storage must be an existing absolute directory")
    if root.is_symlink():
        raise GiftStorageUnavailable("Gift storage root cannot be a symlink")
    marker = root / (".gift-preflight-" + secrets.token_hex(12))
    try:
        with marker.open("xb") as stream:
            stream.write(b"food-porn-gift-storage-v1")
            stream.flush()
            os.fsync(stream.fileno())
        if marker.read_bytes() != b"food-porn-gift-storage-v1":
            raise GiftStorageUnavailable("Gift storage write verification failed")
    except OSError as exc:
        raise GiftStorageUnavailable("Gift storage is not writable") from exc
    finally:
        marker.unlink(missing_ok=True)
