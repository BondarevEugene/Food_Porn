"""Offline regression tests for the paid digital PDF release gate."""
from io import BytesIO

import pytest
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A5
from reportlab.pdfgen import canvas

from app.little_legend.digital_delivery_gate import validate_paid_digital_pdf
from app.little_legend.illustrated_pdf import render_illustrated_proof
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def approved_book(*, edition: str) -> bytes:
    graph = build_graph(["Открытие сада"])
    manuscript = StoryManuscript(
        hero_name="Марта", parent_approved=True,
        chapters=[ChapterDraft(
            scene_id="scene_1", text="Марта вошла в сад.", approved=True,
        )],
    )
    image = BytesIO()
    PILImage.new("RGB", (600, 600), "white").save(image, format="PNG")
    return render_illustrated_proof(
        title="Сказка Марты", dedication="С любовью",
        graph=graph, manuscript=manuscript,
        illustrations={"scene_1": image.getvalue()},
        approved_scene_ids={"scene_1"}, edition=edition,
    )


def test_approved_digital_book_passes_gate():
    validate_paid_digital_pdf(approved_book(edition="digital"), expected_scenes=1)


def test_editorial_proof_is_not_deliverable():
    with pytest.raises(ValueError, match="Editorial"):
        validate_paid_digital_pdf(
            approved_book(edition="editorial_proof"), expected_scenes=1
        )


def test_truncated_pdf_is_rejected():
    with pytest.raises(ValueError):
        validate_paid_digital_pdf(b"%PDF-broken", expected_scenes=1)


def test_unexpected_scene_count_is_rejected():
    with pytest.raises(ValueError, match="page-count|chapters"):
        validate_paid_digital_pdf(approved_book(edition="digital"), expected_scenes=10)


def test_pdf_without_approved_cover_art_is_rejected():
    output = BytesIO()
    doc = canvas.Canvas(output, pagesize=A5)
    for text in ("Cover", "Dedication", "Глава 1. Test"):
        doc.drawString(50, 300, text)
        doc.showPage()
    doc.save()
    with pytest.raises(ValueError, match="cover illustration"):
        validate_paid_digital_pdf(output.getvalue(), expected_scenes=1)


def test_invalid_scene_count_is_rejected():
    with pytest.raises(ValueError, match="scene count"):
        validate_paid_digital_pdf(b"", expected_scenes=0)
