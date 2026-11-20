"""Illustration launch must require a complete parent-approved manuscript."""
from app.bot.handlers.little_legend_illustrations import approved_scene_ids
from app.little_legend.router import StoryDraft
from app.little_legend.story_writer import StoryManuscript


def test_missing_graph_or_manuscript_blocks_art_launch():
    assert approved_scene_ids(StoryDraft()) == []
    assert approved_scene_ids(
        StoryDraft(manuscript=StoryManuscript(hero_name="Оля"))
    ) == []


def test_parent_approval_is_not_inferred_from_chapter_count():
    assert approved_scene_ids(
        StoryDraft(manuscript=StoryManuscript(
            hero_name="Оля", parent_approved=True,
        ))
    ) == []
