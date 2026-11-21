"""Offline typography and page-geometry audit for Little Legend PDFs.

This detects objective digital-layout defects; it cannot certify printing,
visual beauty, font rendering quality or child likeness.
"""
from __future__ import annotations

from io import BytesIO

from pydantic import BaseModel, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.little_legend.pdf_preflight import MAX_PDF_BYTES

A5_WIDTH_PT = 419.527559
A5_HEIGHT_PT = 595.275591


class LayoutIssue(BaseModel):
    code: str
    page: int = Field(ge=1)


class LayoutAudit(BaseModel):
    page_count: int = Field(ge=0)
    a5_pages: int = Field(ge=0)
    pages_with_selectable_text: int = Field(ge=0)
    issues: list[LayoutIssue] = Field(default_factory=list)
    digital_layout_valid: bool = False
    print_ready: bool = False


def audit_pdf_layout(
    pdf: bytes,
    *,
    expected_pages_min: int = 3,
    page_tolerance_pt: float = 2.0,
) -> LayoutAudit:
    """Check PDF page boxes, selectable text, and structural text integrity."""
    if expected_pages_min < 1 or page_tolerance_pt < 0:
        raise ValueError("Invalid layout policy")
    if not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF signature")
    if len(pdf) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds configured maximum size")
    try:
        reader = PdfReader(BytesIO(pdf), strict=True)
        issues: list[LayoutIssue] = []
        a5_pages = 0
        text_pages = 0
        for index, page in enumerate(reader.pages, 1):
            media = page.mediabox
            crop = page.cropbox
            width = float(media.width)
            height = float(media.height)
            if (
                abs(width - A5_WIDTH_PT) > page_tolerance_pt
                or abs(height - A5_HEIGHT_PT) > page_tolerance_pt
            ):
                issues.append(LayoutIssue(code="unexpected_page_size", page=index))
            else:
                a5_pages += 1
            if (
                float(crop.left) < float(media.left) - page_tolerance_pt
                or float(crop.bottom) < float(media.bottom) - page_tolerance_pt
                or float(crop.right) > float(media.right) + page_tolerance_pt
                or float(crop.top) > float(media.top) + page_tolerance_pt
                or float(crop.width) <= 0
                or float(crop.height) <= 0
            ):
                issues.append(LayoutIssue(code="invalid_crop_box", page=index))
            text = page.extract_text() or ""
            if not text.strip():
                issues.append(LayoutIssue(code="page_without_selectable_text", page=index))
            else:
                text_pages += 1
            if "\ufffd" in text or "\x00" in text:
                issues.append(LayoutIssue(code="corrupted_text_extraction", page=index))
        count = len(reader.pages)
    except (PdfReadError, KeyError, TypeError, ValueError, OSError) as exc:
        raise ValueError("PDF layout could not be inspected") from exc
    if count < expected_pages_min:
        issues.append(LayoutIssue(code="insufficient_pages", page=1))
    return LayoutAudit(
        page_count=count, a5_pages=a5_pages,
        pages_with_selectable_text=text_pages, issues=issues,
        digital_layout_valid=not issues,
    )
