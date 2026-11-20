"""Offline, privacy-preserving release audit for Little Legend A5 books.

The audit reports stable issue codes, not customer prose or image bytes.
It never certifies printing readiness and never uploads assets.
"""
from __future__ import annotations

from io import BytesIO
from typing import Literal

from pydantic import BaseModel, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.little_legend.book_quality import inspect_illustrated_book
from app.little_legend.digital_delivery_gate import validate_paid_digital_pdf
from app.little_legend.pdf_preflight import MAX_PDF_BYTES

Edition = Literal["digital", "editorial_proof"]


class ReleaseAudit(BaseModel):
    edition: Edition
    deliverable: bool
    print_ready: bool = False
    page_count: int = Field(ge=0)
    expected_scenes: int = Field(ge=1)
    illustration_count: int = Field(ge=0)
    issue_codes: list[str] = Field(default_factory=list)


def audit_book_release(
    *,
    pdf: bytes,
    illustrations: dict[str, bytes],
    expected_scenes: int,
    edition: Edition,
    cover_scene_id: str,
) -> ReleaseAudit:
    """Evaluate objective PDF and artwork checks without leaking customer data.

    A digital book can be delivered only after the existing paid-delivery
    validator passes. Editorial proofs remain explicitly non-deliverable.
    """
    if edition not in ("digital", "editorial_proof"):
        raise ValueError("Unsupported edition")
    if not 1 <= expected_scenes <= 100:
        raise ValueError("Invalid expected scene count")
    if not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF bytes")
    if len(pdf) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds size limit")
    if not cover_scene_id or cover_scene_id not in illustrations:
        raise ValueError("Cover illustration is missing")
    if len(illustrations) != expected_scenes:
        raise ValueError("Illustration count does not match scene count")

    quality = inspect_illustrated_book(
        pdf=pdf,
        illustrations=illustrations,
        expected_min_pages=expected_scenes + 2,
        cover_scene_id=cover_scene_id,
    )
    issues = list(dict.fromkeys(quality.issues))
    try:
        reader = PdfReader(BytesIO(pdf), strict=True)
        chapter_pages = reader.pages[2:]
        pages_with_art = sum(bool(page.images) for page in chapter_pages)
        if pages_with_art < expected_scenes:
            issues.append("chapter_art_missing")
        if any(not (page.extract_text() or "").strip() for page in reader.pages):
            issues.append("blank_or_image_only_page")
    except (PdfReadError, KeyError, ValueError, TypeError, OSError):
        issues.append("pdf_content_unreadable")

    if edition == "digital":
        try:
            validate_paid_digital_pdf(pdf, expected_scenes=expected_scenes)
        except ValueError:
            issues.append("paid_delivery_gate_failed")
    else:
        issues.append("editorial_proof_not_deliverable")

    issues = list(dict.fromkeys(issues))
    # Low-resolution art is a print-quality warning, not a digital blocker.
    blocking = {
        "insufficient_pages",
        "illustrations_missing",
        "chapter_art_missing",
        "blank_or_image_only_page",
        "pdf_content_unreadable",
        "paid_delivery_gate_failed",
        "editorial_proof_not_deliverable",
    }
    return ReleaseAudit(
        edition=edition,
        deliverable=quality.structurally_valid and not blocking.intersection(issues),
        print_ready=False,
        page_count=quality.page_count,
        expected_scenes=expected_scenes,
        illustration_count=len(illustrations),
        issue_codes=issues,
    )
