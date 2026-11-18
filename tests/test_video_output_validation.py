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
    output.write_bytes(b"mock movie")
    validate_rendered_video(output)
