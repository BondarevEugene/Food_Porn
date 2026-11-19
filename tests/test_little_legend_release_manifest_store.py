"""Sealed release manifest validation and migration contract."""
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.release_manifest_store import ReleaseManifest


def test_manifest_rejects_invalid_release_digest() -> None:
    with pytest.raises(ValidationError):
        ReleaseManifest(
            owner_id=1, story_id=2,
            revision_fingerprint="a" * 64,
            pdf_sha256="not-a-digest", scene_count=1,
            status=DeliveryStatus.READY,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )


def test_manifest_has_no_pdf_bytes_or_child_content() -> None:
    manifest = ReleaseManifest(
        owner_id=1, story_id=2,
        revision_fingerprint="a" * 64,
        pdf_sha256="b" * 64, scene_count=3,
        status=DeliveryStatus.READY,
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    assert "pdf" not in manifest.model_fields
    assert "manuscript" not in manifest.model_fields
    assert manifest.telegram_message_id is None
