"""Безпечне накладання перевіреної музики на готове відео через FFmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.music_intelligence import LicensedTrack, MusicCatalogService


class VideoAudioMuxService:
    """Не приймає довільні музичні файли без підтвердженої ліцензії."""

    def __init__(self, ffmpeg_executable: str = "ffmpeg") -> None:
        self.ffmpeg_executable = ffmpeg_executable

    def render(
        self, *,
        video: Path,
        destination: Path,
        duration_seconds: float,
        track: LicensedTrack | None,
    ) -> Path:
        if not video.is_file():
            raise FileNotFoundError("Source video is unavailable")
        if duration_seconds <= 0:
            raise ValueError("Video duration must be positive")
        if track is not None and not MusicCatalogService.eligible(track):
            raise PermissionError("Music license or file integrity is not verified")
        if destination.resolve() == video.resolve():
            raise ValueError("Output must differ from source video")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.stem}.partial{destination.suffix}")
        temporary.unlink(missing_ok=True)
        command = [
            self.ffmpeg_executable, "-y", "-loglevel", "error",
            "-i", str(video),
        ]
        if track is None:
            command += ["-map", "0:v:0", "-an"]
        else:
            fade_out = max(0.0, duration_seconds - min(1.5, duration_seconds / 4))
            command += [
                "-i", str(track.file_path),
                "-filter_complex",
                f"[1:a:0]atrim=duration={duration_seconds:.3f},"
                "asetpts=PTS-STARTPTS,"
                "afade=t=in:st=0:d=0.5,"
                f"afade=t=out:st={fade_out:.3f}:d={duration_seconds-fade_out:.3f},"
                "volume=0.7,alimiter=limit=0.95[a]",
                "-map", "0:v:0", "-map", "[a]",
                "-c:a", "aac", "-b:a", "160k",
            ]
        command += [
            "-c:v", "copy", "-t", str(duration_seconds),
            "-movflags", "+faststart", str(temporary),
        ]
        try:
            subprocess.run(command, check=True, timeout=300, capture_output=True)
            temporary.replace(destination)
        except (OSError, subprocess.SubprocessError):
            temporary.unlink(missing_ok=True)
            raise
        return destination
