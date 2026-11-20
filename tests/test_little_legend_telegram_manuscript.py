"""Parental manuscript approval is an explicit, complete-story decision."""
import pytest

from app.bot.handlers.little_legend_manuscript import (
    _parse,
    approve_complete_manuscript,
    review_text,
)
from app.little_legend.router import StoryDraft
from app.little_legend.story_writer import StoryManuscript


def test_unwritten_story_cannot_be_finally_approved():
    with pytest.raises(ValueError, match="outline"):
        approve_complete_manuscript(
            StoryManuscript(hero_name="Оля"), StoryDraft(),
        )


def test_empty_review_does_not_claim_approval():
    assert "Сначала нужен план" in review_text(StoryDraft())


def test_callback_identifiers_reject_invalid_values():
    class Callback:
        data = "ll_chapter:-1:0"

    assert _parse(Callback(), 2) is None
    Callback.data = "ll_chapter:4:not-an-int"
    assert _parse(Callback(), 2) is None
    Callback.data = "ll_chapter:4:0"
    assert _parse(Callback(), 2) == [4, 0]
