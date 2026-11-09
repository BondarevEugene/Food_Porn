"""Regression tests for customer photo preflight before paid menu generation."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.services.menu_quality import validate_customer_photos


def _menu(cover: str | None, spread: str | None) -> SimpleNamespace:
    return SimpleNamespace(cover_photo_path=cover, spread_photo_path=spread)


def _photo(path: Path) -> str:
    Image.new("RGB", (32, 32), "white").save(path, format="JPEG")
    return str(path)


def test_valid_customer_photos_pass(tmp_path: Path) -> None:
    cover = _photo(tmp_path / "cover.jpg")
    spread = _photo(tmp_path / "spread.jpg")

    validate_customer_photos(_menu(cover, spread))


@pytest.mark.parametrize("missing_role", ["cover", "spread"])
def test_missing_customer_photo_fails(tmp_path: Path, missing_role: str) -> None:
    valid = _photo(tmp_path / "valid.jpg")
    missing = str(tmp_path / "vanished.jpg")
    cover = missing if missing_role == "cover" else valid
    spread = missing if missing_role == "spread" else valid

    with pytest.raises(ValueError, match=f"Customer {missing_role} photo is missing"):
        validate_customer_photos(_menu(cover, spread))


def test_empty_customer_photo_reference_fails(tmp_path: Path) -> None:
    spread = _photo(tmp_path / "spread.jpg")

    with pytest.raises(ValueError, match="Customer cover photo is required"):
        validate_customer_photos(_menu(None, spread))


def test_corrupt_customer_photo_fails(tmp_path: Path) -> None:
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"not an image")
    spread = _photo(tmp_path / "spread.jpg")

    with pytest.raises(ValueError, match="Customer cover photo is unreadable"):
        validate_customer_photos(_menu(str(cover), spread))
