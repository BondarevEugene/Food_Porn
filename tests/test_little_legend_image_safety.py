"""Validation of untrusted Little Legend image bytes."""
import io

import pytest
from PIL import Image

from app.little_legend.image_safety import UnsafeImageError, sanitize_image


def _image(fmt="PNG", *, size=(24, 18), exif=None):
    image = Image.new("RGB", size, (10, 100, 220))
    output = io.BytesIO()
    image.save(output, format=fmt, exif=exif)
    return output.getvalue()


def test_reencodes_and_strips_exif():
    exif = Image.Exif()
    exif[270] = "private child details"
    clean = sanitize_image(_image("JPEG", exif=exif))
    assert clean.content_type == "image/jpeg"
    assert (clean.width, clean.height) == (24, 18)
    with Image.open(io.BytesIO(clean.data)) as image:
        assert image.format == "JPEG"
        assert not image.getexif()
        assert b"private child details" not in clean.data


def test_rejects_invalid_and_unsupported_data():
    for value in (b"", b"not a photo", b"x" * (12 * 1024 * 1024 + 1)):
        with pytest.raises(UnsafeImageError):
            sanitize_image(value)
    with pytest.raises(UnsafeImageError):
        sanitize_image(_image("GIF"))


def test_rejects_excessive_pixel_budget():
    with pytest.raises(UnsafeImageError):
        sanitize_image(_image(size=(5000, 5000)))


def test_png_transparency_is_flattened():
    image = Image.new("RGBA", (4, 4), (255, 0, 0, 0))
    output = io.BytesIO()
    image.save(output, format="PNG")
    clean = sanitize_image(output.getvalue())
    with Image.open(io.BytesIO(clean.data)) as result:
        assert result.mode == "RGB"
        assert result.getpixel((0, 0)) == (255, 255, 255)
