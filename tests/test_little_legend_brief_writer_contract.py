"""Brief-mode intake must retain the source for the existing writer queue."""
from app.little_legend.router import StoryDraft
from app.little_legend.story_modes import (
    SimpleBrief,
    StoryEntry,
    StoryMode,
    brief_outline,
    brief_parent_sketch,
)


def test_brief_preserves_source_moments_for_writer_pipeline():
    brief = SimpleBrief(
        child_hero="Мира",
        characters=["Лис"],
        events=["Мира нашла карту", "Лис помог найти дом"],
    )
    sketch = brief_parent_sketch(brief)
    outline = brief_outline(brief, chapter_count=3)
    draft = StoryDraft(
        hero="Мира",
        entry=StoryEntry(mode=StoryMode.BRIEF, brief=brief),
        parent_sketch=sketch,
        graph=outline.graph,
        design=outline.design,
    )
    restored = StoryDraft.model_validate_json(draft.model_dump_json())
    assert restored.parent_sketch is not None
    assert restored.parent_sketch.moments == brief.events
    assert not restored.outline_approved
    assert not restored.entry.plan_approved
    assert restored.graph is not None
