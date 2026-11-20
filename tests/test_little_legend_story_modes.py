"""Regression checks for new Little Legend story entry modes."""
import pytest
from pydantic import ValidationError

from app.little_legend.router import StoryDraft
from app.little_legend.story_modes import (
    ClassicSource,
    SimpleBrief,
    StoryEntry,
    StoryMode,
    brief_outline,
    classic_adaptation_brief,
    entry_preflight,
)


def test_existing_drafts_default_to_director():
    assert StoryDraft.model_validate({"hero": "Оля"}).entry.mode == StoryMode.DIRECTOR


def test_brief_reuses_existing_outline_without_fabricating_events():
    brief = SimpleBrief(
        child_hero="Маша",
        characters=["Барсик", "Дракон"],
        events=["Нашли замок", "Помогли дракону"],
        moral="Дружба",
    )
    outline = brief_outline(brief, chapter_count=3)
    assert outline.source_only is True
    assert outline.ai_generated is False
    assert outline.source_moments == brief.events
    assert outline.design.theme == "Дружба"


def test_classic_requires_verified_rights_and_plan_approval():
    source = ClassicSource(
        title="Красная Шапочка",
        original_hero="Красная Шапочка",
        child_hero="Маша",
    )
    entry = StoryEntry(mode="classic", classic=source)
    assert not entry_preflight(entry)["ready"]
    assert len(entry_preflight(entry)["blockers"]) == 2
    approved = source.model_copy(update={
        "public_domain_verified": True,
        "verification_note": "Documented original edition rights review",
    })
    ready = StoryEntry(mode="classic", classic=approved, plan_approved=True)
    assert entry_preflight(ready)["ready"]
    assert classic_adaptation_brief(approved)["replacement"]["to"] == "Маша"


def test_photo_references_require_parental_consent():
    with pytest.raises(ValidationError):
        StoryEntry(photo_reference_ids=["private-ref"])


def test_mode_payloads_cannot_be_mixed():
    with pytest.raises(ValidationError):
        StoryEntry(mode="brief", classic=ClassicSource(
            title="Народная сказка", original_hero="Герой", child_hero="Маша",
        ))


def test_blank_events_rejected():
    with pytest.raises(ValidationError):
        SimpleBrief(child_hero="Маша", characters=["Кот"], events=["  "])
