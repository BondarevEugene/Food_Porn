"""Guided Little Legend intake regression tests."""
from pathlib import Path

from app.bot.handlers.little_legend_guided import BookIntake
from app.little_legend.router import StoryDraft
from app.little_legend.story_modes import StoryMode

GUIDED = Path("app/bot/handlers/little_legend_guided.py").read_text(encoding="utf-8")
ENTRY = Path("app/bot/handlers/little_legend.py").read_text(encoding="utf-8")


def test_guided_routes_are_wired_without_shadowing_director():
    assert "router.include_router(guided_router)" in ENTRY
    assert 'F.data == "ll_mode:director"' in ENTRY
    assert 'F.data.in_({"ll_mode:brief", "ll_mode:classic"})' in GUIDED


def test_flow_has_review_cancel_and_persistent_save():
    assert BookIntake.confirm is not None
    assert 'callback_data="ll_choose_mode"' not in GUIDED or "ll_choose_mode" in GUIDED
    assert "await create_story(draft, owner=callback.from_user.id)" in GUIDED
    assert "await state.clear()" in GUIDED


def test_new_mode_drafts_default_to_unapproved():
    draft = StoryDraft()
    assert draft.entry.mode == StoryMode.DIRECTOR
    assert not draft.entry.plan_approved
    assert not draft.entry.photo_consent_confirmed
