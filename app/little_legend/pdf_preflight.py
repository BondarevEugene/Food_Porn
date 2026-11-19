"""Offline PDF preflight: report objective defects without claiming print readiness."""
from __future__ import annotations

from io import BytesIO

from pydantic import BaseModel, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_PDF_BYTES = 50 * 1024 * 1024
A5_WIDTH_PT = 419.53
A5_HEIGHT_PT = 595.28


class PDFPreflight(BaseModel):
    valid: bool
    print_ready: bool = False
    page_count: int = Field(ge=0)
    issues: list[str] = Field(default_factory=list)


def inspect_book_pdf(pdf: bytes, *, expected_pages: int | None = None) -> PDFPreflight:
    """Check PDF structure, page geometry and proof markers; no network or writes.

    A structurally valid PDF is not automatically a print-ready product.
    """
    issues: list[str] = []
    if not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF-"):
        return PDFPreflight(valid=False, page_count=0, issues=["invalid_pdf_header"])
    if len(pdf) > MAX_PDF_BYTES:
        return PDFPreflight(valid=False, page_count=0, issues=["pdf_too_large"])
    try:
        reader = PdfReader(BytesIO(pdf), strict=True)
        if reader.is_encrypted:
            return PDFPreflight(valid=False, page_count=0, issues=["encrypted_pdf"])
        count = len(reader.pages)
        if count == 0:
            issues.append("empty_pdf")
        if expected_pages is not None and count != expected_pages:
            issues.append("unexpected_page_count")
        for page in reader.pages:
            box = page.mediabox
            width = float(box.width)
            height = float(box.height)
            if width <= 0 or height <= 0:
                issues.append("invalid_page_geometry")
            elif abs(width - A5_WIDTH_PT) > 2 or abs(height - A5_HEIGHT_PT) > 2:
                issues.append("unexpected_page_size")
            text = page.extract_text() or ""
            if "EDITORIAL PROOF" in text or "НЕ ДЛЯ ТИПОГРАФИИ" in text:
                if "editorial_proof_only" not in issues:
                    issues.append("editorial_proof_only")
    except (PdfReadError, ValueError, TypeError, KeyError, OSError):
        return PDFPreflight(valid=False, page_count=0, issues=["corrupt_pdf"])
    return PDFPreflight(
        valid=not any(issue in issues for issue in (
            "empty_pdf", "unexpected_page_count", "invalid_page_geometry",
            "unexpected_page_size",
        )),
        print_ready=False,
        page_count=count,
        issues=issues,
    )
