"""A5 digital-layout checks never certify print production."""
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A5, A4
from reportlab.pdfgen.canvas import Canvas

from app.little_legend.premium_layout_audit import audit_pdf_layout


def _pdf(*, pages=3, size=A5, blank_page=None):
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=size)
    for index in range(1, pages + 1):
        if index != blank_page:
            canvas.drawString(70, 100, f"Chapter {index}")
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def test_complete_a5_pdf_has_selectable_text_and_valid_geometry():
    report = audit_pdf_layout(_pdf())
    assert report.digital_layout_valid
    assert report.page_count == 3
    assert report.a5_pages == 3
    assert report.pages_with_selectable_text == 3
    assert not report.print_ready


def test_reject_non_a5_pages():
    report = audit_pdf_layout(_pdf(size=A4))
    assert not report.digital_layout_valid
    assert {issue.code for issue in report.issues} == {"unexpected_page_size"}


def test_reject_blank_pages():
    report = audit_pdf_layout(_pdf(blank_page=2))
    assert not report.digital_layout_valid
    assert ("page_without_selectable_text", 2) in {
        (issue.code, issue.page) for issue in report.issues
    }


def test_reject_short_document():
    report = audit_pdf_layout(_pdf(pages=2))
    assert not report.digital_layout_valid
    assert "insufficient_pages" in {issue.code for issue in report.issues}


def test_reject_crop_box_outside_media_box():
    reader = PdfReader(BytesIO(_pdf()))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.pages[1].cropbox.upper_right = (999, 999)
    output = BytesIO()
    writer.write(output)
    report = audit_pdf_layout(output.getvalue())
    assert ("invalid_crop_box", 2) in {
        (issue.code, issue.page) for issue in report.issues
    }


def test_reject_invalid_bytes_and_policy():
    with pytest.raises(ValueError):
        audit_pdf_layout(b"not a pdf")
    with pytest.raises(ValueError):
        audit_pdf_layout(_pdf(), expected_pages_min=0)
