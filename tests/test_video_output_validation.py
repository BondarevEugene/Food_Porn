"""Guard against reporting missing or empty video output as ready."""
from pathlib import Path

import pytest

from app.services.video_story_render import validate_rendered_video


def test_missing_mp4_is_rejected(tmp_path: Path):
    with pytest.raises(RuntimeError, match="no playable file"):
        validate_rendered_video(tmp_path / "missing.mp4")


def test_empty_mp4_is_rejected(tmp_path: Path):
    output = tmp_path / "empty.mp4"
    output.touch()
    with pytest.raises(RuntimeError, match="no playable file"):
        validate_rendered_video(output)


def test_nonempty_mp4_passes_basic_presence_check(tmp_path: Path):
    output = tmp_path / "story.mp4"
    output.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 1012)
    validate_rendered_video(output)


def test_non_mp4_bytes_are_rejected(tmp_path: Path):
    output = tmp_path / "broken.mp4"
    output.write_bytes(b"x" * 2048)
    with pytest.raises(RuntimeError, match="invalid MP4"):
        validate_rendered_video(output)
