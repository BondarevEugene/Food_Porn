"""Prepare a customer-owned poster package after the payment has been verified."""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image

from app.services.replicate_vision_board import ReplicateVisionBoardRenderer


def create_print_bundle(
    order_id: int, mobile: Path, desktop: Path, *,
    width_mm: int = 300, height_mm: int = 400, dpi: int = 300,
) -> Path:
    """Make one reproducible ZIP with a poster, its PDF, and the two originals.

    The poster preserves the whole 9:16 work by extending the sides with a
    blurred copy; a 300 DPI file made from 1080 pixels cannot gain real detail.
    """
    if order_id < 1 or not mobile.is_file() or not desktop.is_file():
        raise ValueError("A valid order and both original files are required")
    folder = mobile.parent
    archive = folder / f"print_order_{order_id}.zip"
    poster_name = f"poster_{width_mm}x{height_mm}mm_{dpi}dpi.png"
    pdf_name = f"poster_{width_mm}x{height_mm}mm.pdf"
    if archive.is_file():
        with ZipFile(archive) as existing:
            if existing.testzip() is None and {
                poster_name, pdf_name,
                "mobile_original.png", "desktop_original.png", "PRINT_INFO.txt",
            } <= set(existing.namelist()):
                return archive
    renderer = ReplicateVisionBoardRenderer(output_dir=folder)
    poster = renderer._print_sync(order_id, str(mobile), width_mm, height_mm, dpi, 3)
    pdf = folder / f"print_order_{order_id}.pdf"
    with Image.open(poster) as opened:
        rgb = opened.convert("RGB")
        rgb.save(pdf, "PDF", resolution=dpi, quality=95)
    with Image.open(mobile) as opened:
        source_width = opened.width
    effective_dpi = round(source_width / (height_mm * 9 / 16 / 25.4))
    info = (
        f"Order: {order_id}\nPoster: {width_mm} x {height_mm} mm + 3 mm bleed on each side\n"
        f"Raster/PDF metadata: {dpi} DPI; RGB. Please confirm CMYK and paper with your printer.\n"
        "The entire phone artwork is visible; the sides are extended softly for 3:4 paper.\n"
        f"Original detail is approximately {effective_dpi} DPI at the displayed image width; "
        "resizing cannot create missing detail. Check a proof before a large print run.\n"
    )
    temp = archive.with_name(f".{archive.stem}.{uuid.uuid4().hex}.tmp.zip")
    try:
        with ZipFile(temp, "w", ZIP_DEFLATED, compresslevel=6) as bundle:
            bundle.write(poster, poster_name)
            bundle.write(pdf, pdf_name)
            bundle.write(mobile, "mobile_original.png")
            bundle.write(desktop, "desktop_original.png")
            bundle.writestr("PRINT_INFO.txt", info)
        os.replace(temp, archive)
    finally:
        temp.unlink(missing_ok=True)
    return archive
