"""Production checkpoint transitions are version-fenced and fail closed."""
import pytest

from app.little_legend.production_checkpoint import (
    ProductionCheckpoint,
    ProductionPhase,
    advance_checkpoint,
    requires_resume,
)


def _advance(checkpoint, phase, **kwargs):
    return advance_checkpoint(
        checkpoint, expected_version=checkpoint.version,
        next_phase=phase, **kwargs,
    )


def test_complete_production_tracks_versions_and_evidence():
    checkpoint = ProductionCheckpoint(owner_id=3, story_id=2)
    checkpoint = _advance(checkpoint, ProductionPhase.MANUSCRIPT_APPROVED)
    checkpoint = _advance(checkpoint, ProductionPhase.ART_APPROVED)
    checkpoint = _advance(
        checkpoint, ProductionPhase.PDF_SEALED,
        release_fingerprint="a" * 64, pdf_sha256="b" * 64,
    )
    checkpoint = _advance(checkpoint, ProductionPhase.DELIVERY_PENDING)
    assert requires_resume(checkpoint)
    checkpoint = _advance(
        checkpoint, ProductionPhase.DELIVERED, delivery_message_id=42,
    )
    assert checkpoint.version == 5
    assert checkpoint.delivery_message_id == 42
    assert not requires_resume(checkpoint)


def test_stale_worker_cannot_advance_checkpoint():
    checkpoint = ProductionCheckpoint(owner_id=3, story_id=2)
    with pytest.raises(PermissionError, match="Stale"):
        advance_checkpoint(
            checkpoint, expected_version=1,
            next_phase=ProductionPhase.MANUSCRIPT_APPROVED,
        )


def test_skipping_phase_is_rejected():
    checkpoint = ProductionCheckpoint(owner_id=3, story_id=2)
    with pytest.raises(PermissionError, match="Invalid"):
        _advance(checkpoint, ProductionPhase.PDF_SEALED)


def test_pdf_sealing_requires_release_and_hash():
    checkpoint = ProductionCheckpoint(owner_id=3, story_id=2)
    checkpoint = _advance(checkpoint, ProductionPhase.MANUSCRIPT_APPROVED)
    checkpoint = _advance(checkpoint, ProductionPhase.ART_APPROVED)
    with pytest.raises(PermissionError, match="verification"):
        _advance(checkpoint, ProductionPhase.PDF_SEALED)


def test_sealed_pdf_and_release_cannot_be_changed():
    checkpoint = ProductionCheckpoint(owner_id=3, story_id=2)
    checkpoint = _advance(checkpoint, ProductionPhase.MANUSCRIPT_APPROVED)
    checkpoint = _advance(checkpoint, ProductionPhase.ART_APPROVED)
    checkpoint = _advance(
        checkpoint, ProductionPhase.PDF_SEALED,
        release_fingerprint="a" * 64, pdf_sha256="b" * 64,
    )
    with pytest.raises(PermissionError, match="Sealed PDF"):
        _advance(
            checkpoint, ProductionPhase.DELIVERY_PENDING,
            pdf_sha256="c" * 64,
        )


def test_delivery_cannot_be_marked_complete_without_message():
    checkpoint = ProductionCheckpoint(owner_id=3, story_id=2)
    checkpoint = _advance(checkpoint, ProductionPhase.MANUSCRIPT_APPROVED)
    checkpoint = _advance(checkpoint, ProductionPhase.ART_APPROVED)
    checkpoint = _advance(
        checkpoint, ProductionPhase.PDF_SEALED,
        release_fingerprint="a" * 64, pdf_sha256="b" * 64,
    )
    checkpoint = _advance(checkpoint, ProductionPhase.DELIVERY_PENDING)
    with pytest.raises(PermissionError, match="Confirmed"):
        _advance(checkpoint, ProductionPhase.DELIVERED)
