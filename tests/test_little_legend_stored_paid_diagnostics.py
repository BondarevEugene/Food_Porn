"""Stored paid PDF diagnostics are bounded, read-only and privacy-safe."""

from io import BytesIO

from reportlab.lib.pagesizes import A5
from reportlab.pdfgen.canvas import Canvas

from app.little_legend.stored_paid_diagnostics import diagnose_stored_paid_pdf


def _pdf(*, pages=3):
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=A5)
    for index in range(pages):
        canvas.drawString(36, 450, f"Page {index + 1}")
        canvas.showPage()
    canvas.save()
    return stream.getvalue()


def test_rejects_invalid_pdf_without_exposing_bytes():
    result = diagnose_stored_paid_pdf(b"not pdf")
    assert result.status == "blocked"
    assert result.issue_codes
    assert "pdf" not in result.model_dump()


def test_rejects_oversized_pdf_without_parsing():
    result = diagnose_stored_paid_pdf(b"%PDF-" + b"x" * (50 * 1024 * 1024 + 1))
    assert result.status == "blocked"
    assert result.issue_codes == ["invalid_pdf_bytes"]


def test_detects_missing_cover_art_and_chapter_text():
    result = diagnose_stored_paid_pdf(_pdf())
    assert result.status == "blocked"
    assert not result.cover_has_art
    assert "cover_art_missing" in result.issue_codes
    assert "chapter_text_missing" in result.issue_codes
    assert not result.print_ready


def test_rejects_too_few_pages():
    result = diagnose_stored_paid_pdf(_pdf(pages=1))
    assert result.status == "blocked"
    assert "insufficient_pages" in result.issue_codes
