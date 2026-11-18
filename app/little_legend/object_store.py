"""Private S3-compatible object store adapter for Little Legend.

Internal service only: no HTTP upload/download endpoint and no public URLs.
Bucket policy, IAM restrictions and parental consent must be configured separately.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.little_legend.image_safety import SanitizedImage
from app.little_legend.secure_vault import VaultAsset, authorize_asset


class ObjectStore(Protocol):
    def put(self, *, key: str, data: bytes, content_type: str) -> None: ...
    def delete(self, *, key: str) -> None: ...


@dataclass(frozen=True)
class S3Settings:
    endpoint_url: str
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str

    def __post_init__(self) -> None:
        if not self.endpoint_url.startswith("https://"):
            raise ValueError("Object storage endpoint must use HTTPS")
        if not all((
            self.bucket, self.region, self.access_key_id, self.secret_access_key
        )):
            raise ValueError("Object storage configuration is incomplete")


class S3PrivateStore:
    """S3-compatible private bucket; credentials must never be logged."""

    def __init__(self, settings: S3Settings) -> None:
        import boto3

        self._bucket = settings.bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            region_name=settings.region,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
        )

    def put(self, *, key: str, data: bytes, content_type: str) -> None:
        _validate_key(key)
        if content_type != "image/jpeg":
            raise ValueError("Only sanitized JPEG is accepted")
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl="private, no-store",
            Metadata={"kind": "little-legend-private-photo"},
        )

    def delete(self, *, key: str) -> None:
        _validate_key(key)
        self._client.delete_object(Bucket=self._bucket, Key=key)


def _validate_key(key: str) -> None:
    prefix = "little-legend/private/"
    suffix = key.removeprefix(prefix)
    if (
        not key.startswith(prefix)
        or len(suffix) != 48
        or any(char not in "0123456789abcdef" for char in suffix)
    ):
        raise ValueError("Invalid private object key")


def store_sanitized_photo(
    store: ObjectStore, *, asset: VaultAsset, owner_id: int,
    story_id: int, image: SanitizedImage, consent_verified: bool = False,
) -> None:
    """Require caller-verified consent and ownership before writing bytes.

    This helper does not transition database state. The caller must reconcile
    successful writes with the registry and clean up on transaction failure.
    """
    authorize_asset(asset, owner_id=owner_id, story_id=story_id)
    if not consent_verified:
        raise PermissionError("Verified parental consent required")
    if asset.state.value != "reserved":
        raise ValueError("Asset must be reserved")
    if image.content_type != "image/jpeg":
        raise ValueError("Sanitized JPEG required")
    _validate_key(asset.object_key)
    store.put(key=asset.object_key, data=image.data, content_type=image.content_type)
