"""Version-fenced checkpoints for a restart-safe book production pipeline.

Pure state transitions. Persist checkpoints with compare-and-swap in the
repository layer before starting any external work.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ProductionPhase(StrEnum):
    DRAFT = "draft"
    MANUSCRIPT_APPROVED = "manuscript_approved"
    ART_APPROVED = "art_approved"
    PDF_SEALED = "pdf_sealed"
    DELIVERY_PENDING = "delivery_pending"
    DELIVERED = "delivered"


_NEXT: dict[ProductionPhase, ProductionPhase] = {
    ProductionPhase.DRAFT: ProductionPhase.MANUSCRIPT_APPROVED,
    ProductionPhase.MANUSCRIPT_APPROVED: ProductionPhase.ART_APPROVED,
    ProductionPhase.ART_APPROVED: ProductionPhase.PDF_SEALED,
    ProductionPhase.PDF_SEALED: ProductionPhase.DELIVERY_PENDING,
    ProductionPhase.DELIVERY_PENDING: ProductionPhase.DELIVERED,
}


class ProductionCheckpoint(BaseModel):
    owner_id: int = Field(gt=0)
    story_id: int = Field(gt=0)
    version: int = Field(default=0, ge=0)
    phase: ProductionPhase = ProductionPhase.DRAFT
    release_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    pdf_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    delivery_message_id: int | None = Field(default=None, gt=0)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def advance_checkpoint(
    checkpoint: ProductionCheckpoint, *, expected_version: int,
    next_phase: ProductionPhase, release_fingerprint: str | None = None,
    pdf_sha256: str | None = None, delivery_message_id: int | None = None,
) -> ProductionCheckpoint:
    """Reject stale workers, skipped stages and incomplete publication evidence."""
    if checkpoint.version != expected_version:
        raise PermissionError("Stale production checkpoint version")
    if _NEXT.get(checkpoint.phase) != next_phase:
        raise PermissionError("Invalid production phase transition")
    fingerprint = release_fingerprint or checkpoint.release_fingerprint
    pdf_hash = pdf_sha256 or checkpoint.pdf_sha256
    if checkpoint.release_fingerprint is not None and (
        release_fingerprint is not None
        and release_fingerprint != checkpoint.release_fingerprint
    ):
        raise PermissionError("Approved release fingerprint cannot change")
    if checkpoint.pdf_sha256 is not None and (
        pdf_sha256 is not None and pdf_sha256 != checkpoint.pdf_sha256
    ):
        raise PermissionError("Sealed PDF cannot change")
    if next_phase in {
        ProductionPhase.PDF_SEALED, ProductionPhase.DELIVERY_PENDING,
        ProductionPhase.DELIVERED,
    } and (fingerprint is None or pdf_hash is None):
        raise PermissionError("Release and PDF verification are required")
    if next_phase == ProductionPhase.DELIVERED and (
        delivery_message_id is None or delivery_message_id <= 0
    ):
        raise PermissionError("Confirmed delivery message is required")
    if next_phase != ProductionPhase.DELIVERED and delivery_message_id is not None:
        raise PermissionError("Delivery acknowledgement is premature")
    return checkpoint.model_copy(update={
        "phase": next_phase, "version": checkpoint.version + 1,
        "release_fingerprint": fingerprint, "pdf_sha256": pdf_hash,
        "delivery_message_id": delivery_message_id,
        "updated_at": datetime.now(UTC),
    })


def requires_resume(checkpoint: ProductionCheckpoint) -> bool:
    """An unfinished checkpoint is a candidate for explicit recovery."""
    return checkpoint.phase != ProductionPhase.DELIVERED
