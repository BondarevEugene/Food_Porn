"""Private durable storage for finished Little Legend digital editions."""
from __future__ import annotations

import hashlib
import os

MAX_PDF_BYTES = 32 * 1024 * 1024


def pdf_key(*, quote_id: int, owner_id: int) -> str:
    if quote_id <= 0 or owner_id <= 0:
        raise ValueError("Invalid book identity")
    digest = hashlib.sha256(f"{owner_id}:{quote_id}".encode()).hexdigest()
    return f"little-legend/books/{digest}.pdf"


class PaidBookStore:
    """S3-compatible private bucket; never create public URLs."""

    def __init__(self) -> None:
        import boto3

        endpoint = os.environ.get("LITTLE_LEGEND_S3_ENDPOINT_URL", "")
        bucket = os.environ.get("LITTLE_LEGEND_S3_BUCKET", "")
        region = os.environ.get("LITTLE_LEGEND_S3_REGION", "")
        access = os.environ.get("LITTLE_LEGEND_S3_ACCESS_KEY_ID", "")
        secret = os.environ.get("LITTLE_LEGEND_S3_SECRET_ACCESS_KEY", "")
        if not endpoint.startswith("https://") or not all(
            (bucket, region, access, secret)
        ):
            raise RuntimeError("Private book storage is not configured")
        self.bucket = bucket
        self.client = boto3.client(
            "s3", endpoint_url=endpoint, region_name=region,
            aws_access_key_id=access, aws_secret_access_key=secret,
        )

    @staticmethod
    def validate(data: bytes) -> None:
        if not isinstance(data, bytes) or not data.startswith(b"%PDF-"):
            raise ValueError("Invalid book PDF")
        if len(data) > MAX_PDF_BYTES:
            raise ValueError("Book PDF exceeds size limit")

    def put(self, *, key: str, data: bytes) -> None:
        self.validate(data)
        if not key.startswith("little-legend/books/") or not key.endswith(".pdf"):
            raise ValueError("Invalid book key")
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data,
            ContentType="application/pdf", CacheControl="private, no-store",
        )

    def get(self, *, key: str) -> bytes:
        if not key.startswith("little-legend/books/") or not key.endswith(".pdf"):
            raise ValueError("Invalid book key")
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"]
        try:
            data = body.read(MAX_PDF_BYTES + 1)
        finally:
            body.close()
        self.validate(data)
        return data
