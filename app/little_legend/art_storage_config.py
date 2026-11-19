"""Explicit generated-art store configuration for owner-approved book assembly."""
from __future__ import annotations

import os

from app.little_legend.generated_art_store import (
    GeneratedArtS3Settings,
    S3GeneratedArtStore,
)


def configured_generated_art_store() -> S3GeneratedArtStore:
    """Use a private S3 namespace; never fall back to public or local storage."""
    names = (
        "LITTLE_LEGEND_S3_ENDPOINT_URL",
        "LITTLE_LEGEND_S3_BUCKET",
        "LITTLE_LEGEND_S3_REGION",
        "LITTLE_LEGEND_S3_ACCESS_KEY_ID",
        "LITTLE_LEGEND_S3_SECRET_ACCESS_KEY",
    )
    values = [os.environ.get(name, "").strip() for name in names]
    if not all(values):
        raise ValueError("Little Legend generated-art storage is not configured")
    return S3GeneratedArtStore(GeneratedArtS3Settings(*values))
