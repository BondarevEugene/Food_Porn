"""Read-only, bounded diagnostics for an already stored paid digital PDF."""
from __future__ import annotations

from io import BytesIO

from pydantic import BaseModel, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.little_legend.digital_delivery_gate import FORBIDDEN_NOTICES
from app.little_legend.pdf_preflight import MAX_PDF_BYTES, inspect_book_pdf


class StoredBookDiagnostics(BaseModel):
    status: str
    page_count: int = Field(ge=0)
    cover_has_art: bool
    chapter_count: int = Field(ge=0)
    issue_codes: list[str] = Field(default_factory=list)
    print_ready: bool = False


def diagnose_stored_paid_pdf(pdf: bytes) -> StoredBookDiagnostics:
    """Inspect in memory without story text, photo bytes or storage writes.

    This is an operator diagnostic, not a substitute for the production
    release gate, because the expected scene count is not available here.
    """
    if not isinstance(pdf, bytes) or len(pdf) > MAX_PDF_BYTES:
        return StoredBookDiagnostics(
            status="blocked", page_count=0, cover_has_art=False,
            chapter_count=0, issue_codes=["invalid_pdf_bytes"],
        )
    report = inspect_book_pdf(pdf)
    issues = list(report.issues)
    cover_has_art = False
    chapter_count = 0
    try:
        reader = PdfReader(BytesIO(pdf), strict=True)
        if reader.is_encrypted or not reader.pages:
            issues.append("unreadable_or_empty_pdf")
        else:
            cover_has_art = bool(reader.pages[0].images)
            if not cover_has_art:
                issues.append("cover_art_missing")
            texts = [page.extract_text() or "" for page in reader.pages]
            chapter_count = sum("Глава " in text for text in texts[2:])
            if chapter_count == 0:
                issues.append("chapter_text_missing")
            if len(texts) < 3:
                issues.append("insufficient_pages")
            if any(marker in text for text in texts for marker in FORBIDDEN_NOTICES):
                issues.append("editorial_notice_present")
            if any(not text.strip() for text in texts):
                issues.append("blank_or_image_only_page")
    except (PdfReadError, KeyError, TypeError, ValueError, OSError):
        issues.append("pdf_content_unreadable")
    issues = list(dict.fromkeys(issues))
    return StoredBookDiagnostics(
        status="ready" if report.valid and not issues else "blocked",
        page_count=report.page_count, cover_has_art=cover_has_art,
        chapter_count=chapter_count, issue_codes=issues,
    )
