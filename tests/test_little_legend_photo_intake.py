"""Photo consent and no-charge draft safeguards."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.little_legend.story_modes import StoryEntry, StoryMode

SOURCE = Path("app/bot/handlers/little_legend_guided.py").read_text(encoding="utf-8")


def test_photo_references_require_explicit_consent():
    with pytest.raises(ValidationError):
        StoryEntry(mode=StoryMode.DIRECTOR, photo_reference_ids=["telegram-file-id"])
    entry = StoryEntry(
        photo_reference_ids=["telegram-file-id"], photo_consent_confirmed=True,
    )
    assert entry.photo_reference_ids == ["telegram-file-id"]
    assert not entry.plan_approved


def test_guided_photo_flow_never_downloads_or_generates():
    assert "BookIntake.photo_consent" in SOURCE
    assert "BookIntake.photos" in SOURCE
    assert "message.photo[-1].file_id" in SOURCE
    assert "photo_consent_confirmed=data.get" in SOURCE
    assert "await create_story(draft, owner=callback.from_user.id)" in SOURCE
    assert "download_file" not in SOURCE
    assert "generate_image" not in SOURCE


def test_double_save_guard_and_retry_path():
    assert 'if data.get("saving"):' in SOURCE
    assert "await state.update_data(saving=True)" in SOURCE
    assert "await state.update_data(saving=False)" in SOURCE
