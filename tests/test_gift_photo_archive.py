"""Gift source snapshots survive deletion of the temporary Telegram upload."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.config import Settings
from app.services.gift_photo_archive import stage_paid_gift_photos


def _settings(tmp_path):
    return Settings(_env_file=None, storage_root=tmp_path / "persistent")


def _source(settings, user_id=42, label="portrait"):
    folder = settings.uploads_dir / "wallpapers" / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    photo = folder / f"{label}.jpg"
    Image.new("RGB", (300, 400), color="#8f9fba").save(photo)
    return photo


def test_archived_photo_survives_original_upload_deletion(tmp_path):
    settings = _settings(tmp_path)
    uploaded = _source(settings)
    archived = stage_paid_gift_photos(settings, user_id=42, uploads=[uploaded])
    assert archived[0].is_file()
    assert archived[0].is_relative_to(settings.generated_dir.resolve())
    with Image.open(archived[0]) as image:
        image.verify()
    uploaded.unlink()
    assert archived[0].is_file()
    with Image.open(archived[0]) as image:
        assert image.size == (300, 400)


def test_same_photo_is_idempotently_staged(tmp_path):
    settings = _settings(tmp_path)
    uploaded = _source(settings)
    first = stage_paid_gift_photos(settings, user_id=42, uploads=[uploaded])
    second = stage_paid_gift_photos(settings, user_id=42, uploads=[uploaded])
    assert first == second
    assert len(list(first[0].parent.glob("source_*.jpg"))) == 1


def test_mismatched_owner_and_outside_path_are_rejected(tmp_path):
    settings = _settings(tmp_path)
    uploaded = _source(settings)
    with pytest.raises(ValueError, match="does not belong"):
        stage_paid_gift_photos(settings, user_id=43, uploads=[uploaded])
    outsider = tmp_path / "outside.jpg"
    outsider.write_bytes(uploaded.read_bytes())
    with pytest.raises(ValueError, match="does not belong"):
        stage_paid_gift_photos(settings, user_id=42, uploads=[outsider])
    with pytest.raises(ValueError, match="1 to 7"):
        stage_paid_gift_photos(settings, user_id=42, uploads=[])


def test_photo_mutation_creates_distinct_archived_snapshot(tmp_path):
    settings = _settings(tmp_path)
    uploaded = _source(settings)
    first = stage_paid_gift_photos(settings, user_id=42, uploads=[uploaded])
    Image.new("RGB", (300, 400), color="#9c4134").save(uploaded)
    second = stage_paid_gift_photos(settings, user_id=42, uploads=[uploaded])
    assert first[0] != second[0]
    assert first[0].is_file() and second[0].is_file()
