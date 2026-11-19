"""Editorial proof visual contract: no accidental press-ready claims."""
from pathlib import Path

from app.little_legend.illustrated_pdf import MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS


def test_editorial_pdf_has_legible_hierarchy_and_page_furniture():
    source = (Path(__file__).resolve().parents[1]
              / "app/little_legend/illustrated_pdf.py").read_text(encoding="utf-8")
    assert "fontSize=25" in source
    assert "fontSize=16" in source
    assert "leading=18" in source
    assert "L I T T L E   L E G E N D" in source
    assert "EDITORIAL PROOF" in source
    assert "НЕ ДЛЯ ТИПОГРАФИИ" in source


def test_image_validation_limits_remain_in_place():
    assert MAX_IMAGE_BYTES == 12 * 1024 * 1024
    assert MAX_IMAGE_PIXELS == 24_000_000
