"""Fail-closed image byte validation for future Little Legend private uploads.

This is a pure processing utility, NOT an upload endpoint. Never log input bytes.
"""
from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from app.little_legend.secure_vault import MAX_IMAGE_PIXELS, MAX_UPLOAD_BYTES

_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class UnsafeImageError(ValueError):
    """The supplied media is unsuitable for processing."""


@dataclass(frozen=True)
class SanitizedImage:
    data: bytes
    content_type: str
    width: int
    height: int


def sanitize_image(data: bytes) -> SanitizedImage:
    """Decode and re-encode a still image; remove EXIF and other metadata.

    Result is a fresh RGB JPEG, suitable for private storage only after
    separate authorization, parental consent, and object-store integration.
    """
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_UPLOAD_BYTES:
        raise UnsafeImageError("Invalid image size")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in _ALLOWED_FORMATS:
                    raise UnsafeImageError("Unsupported image format")
                width, height = source.size
                if (
                    width <= 0 or height <= 0
                    or width * height > MAX_IMAGE_PIXELS
                    or width > 12000 or height > 12000
                ):
                    raise UnsafeImageError("Image dimensions exceed limits")
                if getattr(source, "n_frames", 1) != 1:
                    raise UnsafeImageError("Animated images are not supported")
                source.load()
                if source.mode in ("RGBA", "LA") or (
                    source.mode == "P" and "transparency" in source.info
                ):
                    rgba = source.convert("RGBA")
                    clean = Image.new("RGB", rgba.size, (255, 255, 255))
                    clean.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    clean = source.convert("RGB")
                with clean:
                    output = io.BytesIO()
                    clean.save(output, format="JPEG", quality=90)
                    return SanitizedImage(
                        data=output.getvalue(),
                        content_type="image/jpeg",
                        width=width,
                        height=height,
                    )
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise UnsafeImageError("Invalid image data") from exc
