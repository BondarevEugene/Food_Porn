"""Private immutable PDF object storage for sealed Little Legend releases.

Only the digest-derived key is exposed to application code. PDFs are never
stored in Neon, served at public URLs or logged.
"""
from __future__ import annotations

import hashlib
from typing import Protocol

from app.little_legend.release_package import ReleasePackage

MAX_PDF_BYTES = 40 * 1024 * 1024


class PrivatePDFStore(Protocol):
    def put(self, *, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, *, key: str) -> bytes: ...


def pdf_object_key(*, owner_id: int, story_id: int, pdf_sha256: str) -> str:
    if owner_id <= 0 or story_id <= 0:
        raise ValueError("Invalid book identity")
    if len(pdf_sha256) != 64 or any(c not in "0123456789abcdef" for c in pdf_sha256):
        raise ValueError("Invalid PDF digest")
    digest = hashlib.sha256(
        f"{owner_id}:{story_id}:{pdf_sha256}".encode("ascii")
    ).hexdigest()
    return f"little-legend/releases/{digest}.pdf"


def validate_pdf(data: bytes, *, expected_sha256: str) -> None:
    if not isinstance(data, bytes) or not 100 <= len(data) <= MAX_PDF_BYTES:
        raise ValueError("Invalid PDF size")
    if not data.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF signature")
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise PermissionError("Stored PDF digest mismatch")


class S3PrivatePDFStore:
    """S3-compatible private storage with bounded reads and no public ACL."""

    def __init__(self, settings) -> None:
        import boto3

        if not settings.endpoint_url.startswith("https://"):
            raise ValueError("Private object storage requires HTTPS")
        self._bucket = settings.bucket
        self._client = boto3.client(
            "s3", endpoint_url=settings.endpoint_url,
            region_name=settings.region,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
        )

    @staticmethod
    def _validate_key(key: str) -> None:
        prefix = "little-legend/releases/"
        suffix = key.removeprefix(prefix)
        if (
            not key.startswith(prefix) or len(suffix) != 68
            or not suffix.endswith(".pdf")
            or any(c not in "0123456789abcdef" for c in suffix[:-4])
        ):
            raise ValueError("Invalid private PDF key")

    def put(self, *, key: str, data: bytes, content_type: str) -> None:
        self._validate_key(key)
        if content_type != "application/pdf":
            raise ValueError("Only PDF objects are accepted")
        if not 100 <= len(data) <= MAX_PDF_BYTES or not data.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF")
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=data,
            ContentType="application/pdf",
            CacheControl="private, no-store",
            Metadata={"kind": "little-legend-release"},
        )

    def get(self, *, key: str) -> bytes:
        self._validate_key(key)
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        body = response["Body"]
        try:
            data = body.read(MAX_PDF_BYTES + 1)
        finally:
            body.close()
        if len(data) > MAX_PDF_BYTES:
            raise ValueError("Stored PDF exceeds size limit")
        return data


def persist_release_pdf(
    *, store: PrivatePDFStore, package: ReleasePackage,
    owner_id: int, story_id: int,
) -> str:
    pdf = package.verified_pdf(owner_id=owner_id, story_id=story_id)
    validate_pdf(pdf, expected_sha256=package.release.pdf_sha256)
    key = pdf_object_key(
        owner_id=owner_id, story_id=story_id,
        pdf_sha256=package.release.pdf_sha256,
    )
    store.put(key=key, data=pdf, content_type="application/pdf")
    return key


def restore_release_pdf(
    *, store: PrivatePDFStore, package: ReleasePackage,
    owner_id: int, story_id: int,
) -> ReleasePackage:
    """Rehydrate bytes only after validating owner and immutable release hash."""
    package.verified_pdf(owner_id=owner_id, story_id=story_id)
    key = pdf_object_key(
        owner_id=owner_id, story_id=story_id,
        pdf_sha256=package.release.pdf_sha256,
    )
    pdf = store.get(key=key)
    validate_pdf(pdf, expected_sha256=package.release.pdf_sha256)
    return package.model_copy(update={"pdf": pdf})
