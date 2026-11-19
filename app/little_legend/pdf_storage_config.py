"""Explicit private PDF storage configuration for Little Legend delivery.

Credentials are loaded only when delivery is requested, never logged.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.little_legend.private_pdf_store import S3PrivatePDFStore


@dataclass(frozen=True)
class PrivatePDFStorageSettings:
    endpoint_url: str
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str


def configured_private_pdf_store() -> S3PrivatePDFStore:
    """Fail closed when any private S3 setting is missing."""
    names = (
        "LITTLE_LEGEND_S3_ENDPOINT_URL",
        "LITTLE_LEGEND_S3_BUCKET",
        "LITTLE_LEGEND_S3_REGION",
        "LITTLE_LEGEND_S3_ACCESS_KEY_ID",
        "LITTLE_LEGEND_S3_SECRET_ACCESS_KEY",
    )
    values = [os.environ.get(name, "").strip() for name in names]
    if not all(values) or not values[0].startswith("https://"):
        raise ValueError("Little Legend private PDF storage is not configured")
    return S3PrivatePDFStore(PrivatePDFStorageSettings(*values))
