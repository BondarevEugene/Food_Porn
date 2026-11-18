"""Fail-closed private photo vault foundation for Little Legend.

No upload, download or photo-processing API is enabled. This module only
validates file envelopes and defines persistent lifecycle metadata contracts.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
DEFAULT_RETENTION_DAYS = 7
MAX_RETENTION_DAYS = 30
PHOTO_UPLOAD_ENABLED = False


class AssetState(StrEnum):
    RESERVED = "reserved"
    STORED = "stored"
    DELETION_PENDING = "deletion_pending"
    DELETED = "deleted"
    DELETE_FAILED = "delete_failed"


class MediaEnvelope(BaseModel):
    """Untrusted metadata; checking an envelope does NOT validate file bytes."""

    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    byte_size: int = Field(gt=0, le=MAX_UPLOAD_BYTES)
    width: int = Field(gt=0, le=12000)
    height: int = Field(gt=0, le=12000)

    @model_validator(mode="after")
    def pixel_budget(self) -> MediaEnvelope:
        if self.width * self.height > MAX_IMAGE_PIXELS:
            raise ValueError("Image exceeds pixel budget")
        return self


class VaultAsset(BaseModel):
    """Database metadata; never put this object into a public story response."""

    asset_id: str
    owner_id: int = Field(gt=0)
    story_id: int = Field(gt=0)
    object_key: str
    state: AssetState = AssetState.RESERVED
    created_at: datetime
    expires_at: datetime
    deleted_at: datetime | None = None
    deletion_attempts: int = Field(default=0, ge=0)
    last_error_code: str | None = None


def new_asset_metadata(
    *, owner_id: int, story_id: int, now: datetime | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> VaultAsset:
    if owner_id <= 0 or story_id <= 0:
        raise ValueError("Owner and story must be positive")
    if not 1 <= retention_days <= MAX_RETENTION_DAYS:
        raise ValueError("Retention must be between 1 and 30 days")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    token = secrets.token_hex(24)
    return VaultAsset(
        asset_id=token,
        owner_id=owner_id,
        story_id=story_id,
        object_key="little-legend/private/" + token,
        created_at=instant,
        expires_at=instant + timedelta(days=retention_days),
    )


def authorize_asset(asset: VaultAsset, *, owner_id: int, story_id: int) -> None:
    """Return the same response for unknown/mismatched ownership in API layer."""
    if not (
        hmac.compare_digest(str(asset.owner_id), str(owner_id))
        and hmac.compare_digest(str(asset.story_id), str(story_id))
    ):
        raise PermissionError("Asset not found")


def request_deletion(asset: VaultAsset) -> VaultAsset:
    """Idempotent state transition; does not claim object deletion occurred."""
    if asset.state == AssetState.DELETED:
        return asset.model_copy(deep=True)
    return asset.model_copy(
        update={"state": AssetState.DELETION_PENDING, "last_error_code": None}
    )


def deletion_succeeded(asset: VaultAsset, *, now: datetime | None = None) -> VaultAsset:
    if asset.state != AssetState.DELETION_PENDING:
        raise ValueError("Asset must be pending deletion")
    return asset.model_copy(
        update={
            "state": AssetState.DELETED,
            "deleted_at": now or datetime.now(UTC),
            "last_error_code": None,
        }
    )


def deletion_failed(asset: VaultAsset, *, error_code: str) -> VaultAsset:
    if asset.state != AssetState.DELETION_PENDING:
        raise ValueError("Asset must be pending deletion")
    if not error_code or len(error_code) > 64:
        raise ValueError("Use a short non-sensitive error code")
    return asset.model_copy(
        update={
            "state": AssetState.DELETE_FAILED,
            "deletion_attempts": asset.deletion_attempts + 1,
            "last_error_code": error_code,
        }
    )


def retention_expired(asset: VaultAsset, *, now: datetime) -> bool:
    if now.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    return asset.state != AssetState.DELETED and now >= asset.expires_at


def upload_capability() -> dict:
    return {
        "enabled": PHOTO_UPLOAD_ENABLED,
        "max_bytes": MAX_UPLOAD_BYTES,
        "allowed_types": ["image/jpeg", "image/png", "image/webp"],
        "retention_days_default": DEFAULT_RETENTION_DAYS,
        "storage_backend_connected": False,
        "image_bytes_verified": False,
        "automatic_cleanup_running": False,
    }
