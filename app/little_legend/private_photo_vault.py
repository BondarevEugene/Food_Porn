"""Private R2 photo storage with owner-scoped, expiring metadata authorization.

This module deliberately exposes no public URLs or upload HTTP routes.
Callers must persist VaultAsset metadata transactionally in their own repository.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from app.little_legend.generated_art_store import GeneratedArtS3Settings
from app.little_legend.image_safety import sanitize_image
from app.little_legend.secure_vault import (
    AssetState,
    VaultAsset,
    authorize_asset,
    new_asset_metadata,
)


class VaultMetadataRepository(Protocol):
    async def get_asset(self, *, asset_id: str) -> VaultAsset | None: ...

    async def create_asset(self, *, asset: VaultAsset) -> None: ...

    async def mark_stored(self, *, asset_id: str) -> None: ...


class PrivatePhotoObjectStore(Protocol):
    def put(self, *, key: str, data: bytes) -> None: ...

    def get(self, *, key: str) -> bytes: ...

    def delete(self, *, key: str) -> None: ...


class S3PrivatePhotoStore:
    """Dedicated private photo namespace, never generated-art namespace."""

    def __init__(self, settings: GeneratedArtS3Settings) -> None:
        import boto3

        self._bucket = settings.bucket
        self._client = boto3.client(
            "s3", endpoint_url=settings.endpoint_url,
            region_name=settings.region,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
        )

    @staticmethod
    def _validate_key(key: str) -> None:
        prefix = "little-legend/private/"
        token = key.removeprefix(prefix)
        if (
            not key.startswith(prefix)
            or len(token) != 48
            or any(char not in "0123456789abcdef" for char in token)
        ):
            raise ValueError("Invalid private photo object key")

    def put(self, *, key: str, data: bytes) -> None:
        self._validate_key(key)
        cleaned = sanitize_image(data)
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=cleaned.data,
            ContentType="image/jpeg", CacheControl="private, no-store",
            Metadata={"kind": "little-legend-private-photo"},
        )

    def get(self, *, key: str) -> bytes:
        self._validate_key(key)
        from app.little_legend.secure_vault import MAX_UPLOAD_BYTES

        response = self._client.get_object(Bucket=self._bucket, Key=key)
        body = response["Body"]
        try:
            raw = body.read(MAX_UPLOAD_BYTES + 1)
        finally:
            body.close()
        return sanitize_image(raw).data

    def delete(self, *, key: str) -> None:
        self._validate_key(key)
        self._client.delete_object(Bucket=self._bucket, Key=key)


class AuthorizedPrivatePhotoVault:
    """Concrete reader/preflight for the premium worker and upload service."""

    def __init__(
        self, *, metadata: VaultMetadataRepository,
        objects: PrivatePhotoObjectStore,
    ) -> None:
        self._metadata = metadata
        self._objects = objects

    async def _authorized(
        self, *, owner_id: int, story_id: int, reference_id: str,
    ) -> VaultAsset:
        if owner_id <= 0 or story_id <= 0 or not reference_id:
            raise PermissionError("Asset not found")
        asset = await self._metadata.get_asset(asset_id=reference_id)
        if asset is None:
            raise PermissionError("Asset not found")
        authorize_asset(asset, owner_id=owner_id, story_id=story_id)
        if (
            asset.asset_id != reference_id
            or asset.object_key != f"little-legend/private/{reference_id}"
            or asset.state != AssetState.STORED
            or asset.expires_at <= datetime.now(UTC)
        ):
            raise PermissionError("Asset not found")
        return asset

    async def read_reference(
        self, *, owner_id: int, story_id: int, reference_id: str,
    ) -> bytes:
        asset = await self._authorized(
            owner_id=owner_id, story_id=story_id, reference_id=reference_id,
        )
        return sanitize_image(self._objects.get(key=asset.object_key)).data

    async def check_access(
        self, *, owner_id: int, story_id: int, reference_ids: set[str],
    ) -> None:
        if not reference_ids:
            raise PermissionError("No reference photos")
        for reference_id in sorted(reference_ids):
            asset = await self._authorized(
                owner_id=owner_id, story_id=story_id,
                reference_id=reference_id,
            )
            # Metadata alone is not enough: the object may have been deleted.
            sanitize_image(self._objects.get(key=asset.object_key))

    async def upload_private_photo(
        self, *, owner_id: int, story_id: int, data: bytes,
        consent_confirmed: bool,
    ) -> VaultAsset:
        if not consent_confirmed:
            raise PermissionError("Parental photo consent required")
        clean = sanitize_image(data)
        asset = new_asset_metadata(owner_id=owner_id, story_id=story_id)
        await self._metadata.create_asset(asset=asset)
        self._objects.put(key=asset.object_key, data=clean.data)
        await self._metadata.mark_stored(asset_id=asset.asset_id)
        return asset.model_copy(update={"state": AssetState.STORED})
