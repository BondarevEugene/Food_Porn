"""Regression checks for Telegram outline review and approval."""
from pathlib import Path

from app.bot.handlers.little_legend_outline import _keyboard, _story_id
from app.little_legend.router import StoryDraft
from app.little_legend.story_modes import StoryEntry, StoryMode

SOURCE = Path("app/bot/handlers/little_legend_outline.py").read_text(encoding="utf-8")
BOOK = Path("app/bot/handlers/little_legend.py").read_text(encoding="utf-8")


def test_outline_navigation_is_wired():
    assert "router.include_router(outline_router)" in BOOK
    assert 'callback_data=f"ll_outline:{story_id}"' in BOOK
    assert _keyboard(7, approvable=True).inline_keyboard[0][0].callback_data == (
        "ll_outline_approve:7"
    )


def test_approval_is_owner_scoped_and_never_enqueues():
    assert SOURCE.count("stories.c.owner_id == callback.from_user.id") >= 3
    assert "with_for_update()" in SOURCE
    assert "draft.entry.plan_approved = True" in SOURCE
    assert "draft.outline_approved = True" in SOURCE
    assert "enqueue_sketch_chapters" not in SOURCE


def test_classic_cannot_be_approved_without_rights():
    assert "not draft.entry.classic.public_domain_verified" in SOURCE
    assert not StoryDraft(
        entry=StoryEntry(mode=StoryMode.DIRECTOR),
    ).outline_approved


def test_invalid_story_id_is_rejected():
    class Callback:
        data = "ll_outline_approve:bad"

    assert _story_id(Callback()) is None
