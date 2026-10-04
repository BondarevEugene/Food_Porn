"""
==========================================================
FOOD_PORN

Module: Storage Service Tests
Layer: Test

Responsibilities:
    - Verify accepted images are normalized
    - Verify invalid image payloads are rejected
==========================================================
"""

from io import BytesIO

import pytest
from PIL import Image

from app.config import Settings
from app.services.storage import InvalidImageError, StorageService


def test_valid_image_is_normalized(tmp_path) -> None:
    source = BytesIO()
    Image.new("RGBA", (100, 80), (200, 30, 20, 120)).save(source, "PNG")
    service = StorageService(Settings(storage_root=tmp_path))
    path = service.save_validated_bytes(source.getvalue(), menu_id=7, role="cover")
    assert path.exists()
    with Image.open(path) as saved:
        assert saved.mode == "RGB"
        assert saved.format == "JPEG"


def test_invalid_image_is_rejected(tmp_path) -> None:
    service = StorageService(Settings(storage_root=tmp_path))
    with pytest.raises(InvalidImageError):
        service.save_validated_bytes(b"not an image", menu_id=7, role="cover")
