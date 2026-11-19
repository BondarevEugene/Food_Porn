"""Fail-closed, offline quality gate before a paid digital PDF reaches S3.

This checks a finished PDF, not source text or private child photographs.
It does not claim press readiness or invoke any external service.
"""
from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.little_legend.pdf_preflight import MAX_PDF_BYTES, inspect_book_pdf

FORBIDDEN_NOTICES = (
    "EDITORIAL PROOF",
    "НЕ ДЛЯ ТИПОГРАФИИ",
    "РЕДАКЦИОННЫЙ МАКЕТ",
    "Редакторская информация",
    "ПРОБНЫЙ МАКЕТ",
)


def validate_paid_digital_pdf(pdf: bytes, *, expected_scenes: int) -> None:
    """Reject broken, incomplete or editorial PDFs before paid delivery."""
    if not 1 <= expected_scenes <= 100:
        raise ValueError("Invalid expected scene count")
    if not isinstance(pdf, bytes) or len(pdf) > MAX_PDF_BYTES:
        raise ValueError("Invalid paid PDF size")
    report = inspect_book_pdf(pdf)
    if not report.valid or report.page_count < expected_scenes + 2:
        raise ValueError("Paid PDF structural or page-count failure")
    if "editorial_proof_only" in report.issues:
        raise ValueError("Editorial proof cannot be delivered to a customer")
    try:
        reader = PdfReader(BytesIO(pdf), strict=True)
        texts = [(page.extract_text() or "") for page in reader.pages]
        if any(marker in text for text in texts for marker in FORBIDDEN_NOTICES):
            raise ValueError("Editorial notices found in paid PDF")
        if not texts[0].strip() or not texts[1].strip():
            raise ValueError("Paid PDF cover or dedication is empty")
        # Check cover art first: a synthetic PDF may not embed Cyrillic fonts,
        # but missing approved artwork must still be diagnosed correctly.
        if not reader.pages[0].images:
            raise ValueError("Paid PDF cover illustration is missing")
        # Each chapter must contain selectable text, not only raster artwork.
        chapter_pages = texts[2:]
        if sum("Глава " in text for text in chapter_pages) < expected_scenes:
            raise ValueError("Paid PDF chapters are incomplete")
    except (PdfReadError, KeyError, TypeError, OSError) as exc:
        raise ValueError("Paid PDF content cannot be inspected") from exc
