"""Deterministic quality report for an illustrated A5 editorial edition.

No customer assets leave memory; report contains only aggregate dimensions,
page count and stable issue codes. This is NOT a press certification.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image as PILImage
from pydantic import BaseModel, Field

from app.little_legend.pdf_preflight import inspect_book_pdf

MIN_PRINT_DPI = 300
ILLUSTRATION_WIDTH_PT = 325
ILLUSTRATION_HEIGHT_PT = 285
COVER_WIDTH_PT = 325
COVER_HEIGHT_PT = 210


class IllustrationQuality(BaseModel):
    scene_id: str
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)
    effective_dpi: int = Field(ge=0)
    issues: list[str] = Field(default_factory=list)


class BookQualityReport(BaseModel):
    structurally_valid: bool
    print_ready: bool = False
    page_count: int = Field(ge=0)
    illustrations: list[IllustrationQuality]
    issues: list[str] = Field(default_factory=list)


def inspect_illustration(
    scene_id: str, raw: bytes, *,
    box_width_pt: float = ILLUSTRATION_WIDTH_PT,
    box_height_pt: float = ILLUSTRATION_HEIGHT_PT,
) -> IllustrationQuality:
    """Check real pixel dimensions at the current maximum illustration box."""
    if not raw or len(raw) > 12 * 1024 * 1024:
        raise ValueError("Invalid illustration bytes")
    try:
        with PILImage.open(BytesIO(raw)) as picture:
            width, height = picture.size
            picture.verify()
    except (OSError, SyntaxError, ValueError) as exc:
        raise ValueError("Invalid illustration") from exc
    if width <= 0 or height <= 0:
        raise ValueError("Invalid illustration geometry")
    if box_width_pt <= 0 or box_height_pt <= 0:
        raise ValueError("Invalid illustration display box")
    scale = min(box_width_pt / width, box_height_pt / height)
    effective_dpi = int(72 / scale)
    issues = ["illustration_below_300_dpi"] if effective_dpi < MIN_PRINT_DPI else []
    return IllustrationQuality(
        scene_id=scene_id, width_px=width, height_px=height,
        effective_dpi=effective_dpi, issues=issues,
    )


def inspect_illustrated_book(
    *, pdf: bytes, illustrations: dict[str, bytes],
    expected_min_pages: int, cover_scene_id: str | None = None,
) -> BookQualityReport:
    """Aggregate objective diagnostics without story prose or child photos."""
    if expected_min_pages < 1:
        raise ValueError("Expected page count must be positive")
    preflight = inspect_book_pdf(pdf)
    images = [
        inspect_illustration(scene_id, raw)
        for scene_id, raw in sorted(illustrations.items())
    ]
    issues = list(preflight.issues)
    if preflight.page_count < expected_min_pages:
        issues.append("insufficient_pages")
    if not images:
        issues.append("illustrations_missing")
    if any(item.issues for item in images):
        issues.append("low_resolution_illustrations")
    return BookQualityReport(
        structurally_valid=preflight.valid and preflight.page_count >= expected_min_pages,
        print_ready=False, page_count=preflight.page_count,
        illustrations=images, issues=issues,
    )
