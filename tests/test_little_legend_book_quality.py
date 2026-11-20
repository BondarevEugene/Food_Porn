"""Quality checks: real PDFs and image DPI without external providers."""
from io import BytesIO

import pytest
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A5
from reportlab.pdfgen import canvas

from app.little_legend.book_quality import (
    inspect_illustrated_book,
    inspect_illustration,
)


def pdf_bytes() -> bytes:
    buffer = BytesIO()
    document = canvas.Canvas(buffer, pagesize=A5)
    document.drawString(40, 400, "LITTLE LEGEND / EDITORIAL PROOF")
    document.showPage()
    document.save()
    return buffer.getvalue()


def image_bytes(size: tuple[int, int]) -> bytes:
    buffer = BytesIO()
    PILImage.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_low_resolution_is_advisory_not_corrupt() -> None:
    result = inspect_illustrated_book(
        pdf=pdf_bytes(), illustrations={"scene_1": image_bytes((600, 600))},
        expected_min_pages=1,
    )
    assert result.structurally_valid
    assert not result.print_ready
    assert "editorial_proof_only" in result.issues
    assert "low_resolution_illustrations" in result.issues
    assert result.illustrations[0].effective_dpi < 300


def test_high_resolution_illustration_meets_300_dpi() -> None:
    result = inspect_illustration("scene_1", image_bytes((1600, 1600)))
    assert result.effective_dpi >= 300
    assert result.issues == []


def test_short_book_fails_quality_gate() -> None:
    result = inspect_illustrated_book(
        pdf=pdf_bytes(), illustrations={"scene_1": image_bytes((600, 600))},
        expected_min_pages=4,
    )
    assert not result.structurally_valid
    assert "insufficient_pages" in result.issues


def test_corrupt_illustration_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid illustration"):
        inspect_illustration("scene_1", b"not an image")


def test_empty_illustration_batch_is_flagged() -> None:
    result = inspect_illustrated_book(
        pdf=pdf_bytes(), illustrations={}, expected_min_pages=1,
    )
    assert "illustrations_missing" in result.issues
    assert not result.print_ready


def test_print_dpi_uses_real_chapter_image_box() -> None:
    result = inspect_illustration("scene_1", image_bytes((1300, 1140)))
    assert result.effective_dpi == 288
    assert "illustration_below_300_dpi" in result.issues


def test_cover_dpi_uses_explicit_first_scene_not_sorted_key() -> None:
    report = inspect_illustrated_book(
        pdf=pdf_bytes(),
        illustrations={
            "scene_10": image_bytes((600, 600)),
            "scene_2": image_bytes((1600, 1600)),
        },
        expected_min_pages=1,
        cover_scene_id="scene_2",
    )
    cover = next(
        item for item in report.illustrations if item.scene_id == "cover:scene_2"
    )
    assert cover.effective_dpi >= 300


def test_missing_cover_scene_is_rejected() -> None:
    with pytest.raises(ValueError, match="Cover scene illustration is missing"):
        inspect_illustrated_book(
            pdf=pdf_bytes(),
            illustrations={"scene_1": image_bytes((600, 600))},
            expected_min_pages=1,
            cover_scene_id="scene_2",
        )
