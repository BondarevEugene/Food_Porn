"""PDF preflight regression tests using local synthetic documents."""
from io import BytesIO

from reportlab.pdfgen import canvas

from app.little_legend.pdf_preflight import inspect_book_pdf


def sample_pdf(*, width: int = 420, height: int = 595, text: str = "Hello") -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=(width, height))
    document.drawString(40, 500, text)
    document.showPage()
    document.save()
    return output.getvalue()


def test_valid_a5_pdf_is_not_assumed_print_ready() -> None:
    result = inspect_book_pdf(sample_pdf(), expected_pages=1)
    assert result.valid
    assert result.page_count == 1
    assert not result.print_ready


def test_editorial_proof_marker_is_reported() -> None:
    result = inspect_book_pdf(sample_pdf(text="LITTLE LEGEND / EDITORIAL PROOF"))
    assert result.valid
    assert "editorial_proof_only" in result.issues
    assert not result.print_ready


def test_wrong_page_size_is_rejected() -> None:
    result = inspect_book_pdf(sample_pdf(width=612, height=792))
    assert not result.valid
    assert "unexpected_page_size" in result.issues


def test_wrong_page_count_is_rejected() -> None:
    result = inspect_book_pdf(sample_pdf(), expected_pages=3)
    assert not result.valid
    assert "unexpected_page_count" in result.issues


def test_invalid_pdf_is_rejected() -> None:
    assert inspect_book_pdf(b"garbage").issues == ["invalid_pdf_header"]
    assert not inspect_book_pdf(b"%PDF-corrupt").valid
