"""Fail-closed, deterministic music selection for paid video stories.

The catalogue contains only manually approved, locally stored recordings.
No network requests or automatic license assumptions are made.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class LicensedTrack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    track_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1)
    author: str = Field(min_length=1)
    file_path: Path
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_url: HttpUrl
    license_name: str = Field(min_length=1)
    license_evidence_path: Path
    verified_by: str = Field(min_length=1)
    verified_at: datetime
    commercial_sync_allowed: bool = False
    customer_delivery_allowed: bool = False
    attribution_required: bool = False
    attribution_text: str = ""
    status: str = "pending"
    moods: tuple[str, ...] = ()
    duration_seconds: float = Field(gt=0)
    energy: float = Field(ge=0, le=1, default=0.5)
    bpm: float = Field(ge=0, le=300, default=0)

    @model_validator(mode="after")
    def validate_attribution(self):
        if self.attribution_required and not self.attribution_text.strip():
            raise ValueError("Required attribution must be provided")
        return self


class MusicRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: str = "auto"
    mood: str = "cinematic"
    ai_voice: bool = False
    duration_seconds: float = Field(default=15, gt=0)


class MusicSelection(BaseModel):
    track_id: str | None
    status: str
    reason: str
    algorithm_version: str = "music-v1"


class MusicCatalogService:
    """Check approval, license evidence and integrity at the point of use."""

    @staticmethod
    def eligible(track: LicensedTrack, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        verified = track.verified_at
        if verified.tzinfo is None:
            return False
        if (
            track.status != "approved"
            or not track.commercial_sync_allowed
            or not track.customer_delivery_allowed
            or verified > now
            or not track.license_evidence_path.is_file()
            or not track.file_path.is_file()
        ):
            return False
        digest = hashlib.sha256()
        try:
            with track.file_path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            return False
        return digest.hexdigest() == track.sha256


class MusicSelectionService:
    """Stable ranking with silence as the safe fallback."""

    def __init__(self, catalogue: list[LicensedTrack]) -> None:
        self.catalogue = catalogue

    def select(self, request: MusicRequest) -> MusicSelection:
        if request.mode == "none":
            return MusicSelection(track_id=None, status="silent", reason="Music disabled")
        if request.mode != "auto":
            raise ValueError("Unsupported music mode")
        candidates = [
            track for track in self.catalogue
            if request.mood in track.moods
            and track.duration_seconds >= request.duration_seconds
            and MusicCatalogService.eligible(track)
        ]
        if not candidates:
            return MusicSelection(
                track_id=None, status="silent",
                reason="No verified commercially licensed music available",
            )
        candidates.sort(
            key=lambda track: (
                abs(track.duration_seconds - request.duration_seconds),
                abs(track.energy - 0.65),
                track.track_id,
            )
        )
        return MusicSelection(
            track_id=candidates[0].track_id,
            status="selected",
            reason="Verified license, matching mood and sufficient duration",
        )
