"""Music Intelligence must fail closed on unverified media."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.music_intelligence import (
    LicensedTrack,
    MusicCatalogService,
    MusicRequest,
    MusicSelectionService,
)


def make_track(tmp_path: Path, **changes) -> LicensedTrack:
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"test audio fixture")
    evidence = tmp_path / "license.txt"
    evidence.write_text("Test-only license evidence", encoding="utf-8")
    values = dict(
        track_id="test-track",
        title="Test score",
        author="Test author",
        file_path=audio,
        sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
        source_url="https://example.org/track",
        license_name="Test commercial sync license",
        license_evidence_path=evidence,
        verified_by="reviewer",
        verified_at=datetime.now(UTC),
        commercial_sync_allowed=True,
        customer_delivery_allowed=True,
        status="approved",
        moods=("cinematic",),
        duration_seconds=20,
    )
    values.update(changes)
    return LicensedTrack(**values)


def test_defaults():
    request = MusicRequest()
    assert (request.mode, request.mood, request.ai_voice) == ("auto", "cinematic", False)


def test_approved_track_selected(tmp_path):
    track = make_track(tmp_path)
    assert MusicCatalogService.eligible(track)
    result = MusicSelectionService([track]).select(MusicRequest())
    assert (result.status, result.track_id) == ("selected", "test-track")


@pytest.mark.parametrize("change", [
    {"status": "pending"},
    {"status": "revoked"},
    {"commercial_sync_allowed": False},
    {"customer_delivery_allowed": False},
    {"sha256": "0" * 64},
])
def test_unverified_track_never_selected(tmp_path, change):
    track = make_track(tmp_path, **change)
    result = MusicSelectionService([track]).select(MusicRequest())
    assert result.status == "silent"
    assert result.track_id is None


def test_missing_license_evidence_fails_closed(tmp_path):
    track = make_track(tmp_path)
    track.license_evidence_path.unlink()
    assert not MusicCatalogService.eligible(track)


def test_tampered_audio_fails_closed(tmp_path):
    track = make_track(tmp_path)
    track.file_path.write_bytes(b"modified")
    assert not MusicCatalogService.eligible(track)


def test_wrong_mood_and_short_audio_fall_back_to_silence(tmp_path):
    track = make_track(tmp_path)
    assert MusicSelectionService([track]).select(MusicRequest(mood="romantic")).status == "silent"
    assert MusicSelectionService([track]).select(MusicRequest(duration_seconds=30)).status == "silent"


def test_music_can_be_disabled(tmp_path):
    track = make_track(tmp_path)
    result = MusicSelectionService([track]).select(MusicRequest(mode="none"))
    assert result.status == "silent"


def test_selection_is_deterministic(tmp_path):
    first = make_track(tmp_path, track_id="a")
    second = make_track(tmp_path, track_id="b")
    selected = MusicSelectionService([second, first]).select(MusicRequest())
    assert selected.track_id == "a"
