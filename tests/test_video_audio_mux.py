"""Перевірки команд FFmpeg без фактичного кодування відео."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.video_audio_mux import VideoAudioMuxService
from tests.test_music_intelligence import make_track


def test_silent_video_does_not_include_music_input(tmp_path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"fixture")
    output = tmp_path / "output.mp4"

    def fake_run(command, **kwargs):
        assert "-an" in command
        assert "-filter_complex" not in command
        Path(command[-1]).write_bytes(b"rendered")
        return subprocess.CompletedProcess(command, 0)

    with patch("app.services.video_audio_mux.subprocess.run", side_effect=fake_run):
        assert VideoAudioMuxService().render(
            video=video, destination=output, duration_seconds=15, track=None
        ) == output


def test_approved_music_uses_fades_and_limiter(tmp_path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"fixture")
    track = make_track(tmp_path)

    def fake_run(command, **kwargs):
        filters = command[command.index("-filter_complex") + 1]
        assert "afade=t=in" in filters
        assert "afade=t=out" in filters
        assert "alimiter" in filters
        assert str(track.file_path) in command
        Path(command[-1]).write_bytes(b"rendered")
        return subprocess.CompletedProcess(command, 0)

    with patch("app.services.video_audio_mux.subprocess.run", side_effect=fake_run):
        VideoAudioMuxService().render(
            video=video, destination=tmp_path / "result.mp4",
            duration_seconds=15, track=track,
        )


def test_revoked_music_never_reaches_ffmpeg(tmp_path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"fixture")
    track = make_track(tmp_path, status="revoked")
    with patch("app.services.video_audio_mux.subprocess.run") as run:
        with pytest.raises(PermissionError):
            VideoAudioMuxService().render(
                video=video, destination=tmp_path / "result.mp4",
                duration_seconds=15, track=track,
            )
        run.assert_not_called()


def test_failed_ffmpeg_does_not_publish_partial_video(tmp_path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"fixture")
    output = tmp_path / "output.mp4"
    with patch("app.services.video_audio_mux.subprocess.run",
               side_effect=subprocess.CalledProcessError(1, ["ffmpeg"])):
        with pytest.raises(subprocess.CalledProcessError):
            VideoAudioMuxService().render(
                video=video, destination=output, duration_seconds=15, track=None
            )
    assert not output.exists()
    assert not list(tmp_path.glob("*.partial.mp4"))
