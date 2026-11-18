"""Private object storage for generated illustration assets.

Generated art uses a separate namespace from parental photo vault assets.
No public URLs or image bytes are stored in Neon.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from app.little_legend.illustrated_pdf import MAX_IMAGE_BYTES


class GeneratedArtStore(Protocol):
    def put(self, *, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, *, key: str) -> bytes: ...
    def delete(self, *, key: str) -> None: ...


def illustration_key(*, owner_id: int, story_id: int, job_id: str) -> str:
    """Deterministic, idempotent key; never use user-supplied path segments."""
    if owner_id <= 0 or story_id <= 0 or not job_id.startswith("lli_"):
        raise ValueError("Invalid illustration asset identity")
    digest = hashlib.sha256(
        f"{owner_id}:{story_id}:{job_id}".encode("utf-8")
    ).hexdigest()
    return f"little-legend/generated/{digest}.jpg"


def validate_generated_art(data: bytes) -> None:
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_IMAGE_BYTES:
        raise ValueError("Invalid generated illustration size")
    if not data.startswith(bytes((255, 216, 255))):
        raise ValueError("Generated illustration must be sanitized JPEG")


@dataclass(frozen=True)
class GeneratedArtS3Settings:
    endpoint_url: str
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str

    def __post_init__(self) -> None:
        if not self.endpoint_url.startswith("https://") or not all((
            self.bucket, self.region, self.access_key_id, self.secret_access_key,
        )):
            raise ValueError("Private generated-art storage is not configured")


class S3GeneratedArtStore:
    def __init__(self, settings: GeneratedArtS3Settings) -> None:
        import boto3

        self._bucket = settings.bucket
        self._client = boto3.client(
            "s3", endpoint_url=settings.endpoint_url, region_name=settings.region,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
        )

    @staticmethod
    def _validate_key(key: str) -> None:
        prefix = "little-legend/generated/"
        suffix = key.removeprefix(prefix)
        if (not key.startswith(prefix) or len(suffix) != 68
                or not suffix.endswith(".jpg")
                or any(c not in "0123456789abcdef" for c in suffix[:-4])):
            raise ValueError("Invalid generated-art key")

    def put(self, *, key: str, data: bytes, content_type: str) -> None:
        self._validate_key(key)
        validate_generated_art(data)
        if content_type != "image/jpeg":
            raise ValueError("Only sanitized JPEG is accepted")
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=data,
            ContentType="image/jpeg", CacheControl="private, no-store",
            Metadata={"kind": "little-legend-generated-art"},
        )

    def get(self, *, key: str) -> bytes:
        self._validate_key(key)
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        body = response["Body"]
        try:
            data = body.read(MAX_IMAGE_BYTES + 1)
        finally:
            body.close()
        validate_generated_art(data)
        return data

    def delete(self, *, key: str) -> None:
        self._validate_key(key)
        self._client.delete_object(Bucket=self._bucket, Key=key)


def save_generated_illustration(
    *, store: GeneratedArtStore, owner_id: int, story_id: int,
    job_id: str, data: bytes,
) -> str:
    validate_generated_art(data)
    key = illustration_key(
        owner_id=owner_id, story_id=story_id, job_id=job_id,
    )
    store.put(key=key, data=data, content_type="image/jpeg")
    return key
