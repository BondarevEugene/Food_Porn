"""Writing readiness remains closed until all approvals are present."""
from app.little_legend.router import StoryDraft
from app.little_legend.story_modes import ClassicSource, StoryEntry, StoryMode
from app.little_legend.telegram_writer_readiness import chapter_readiness


def test_empty_story_is_not_ready():
    report = chapter_readiness(StoryDraft())
    assert not report["ready"]
    assert len(report["blockers"]) >= 3


def test_unverified_classic_is_blocked():
    draft = StoryDraft(
        entry=StoryEntry(
            mode=StoryMode.CLASSIC,
            classic=ClassicSource(
                title="Старая сказка",
                original_hero="Герой",
                child_hero="Мира",
            ),
        ),
    )
    assert any("права" in reason for reason in chapter_readiness(draft)["blockers"])


def test_readiness_has_no_ai_side_effects():
    from pathlib import Path

    source = Path("app/little_legend/telegram_writer_readiness.py").read_text(
        encoding="utf-8",
    )
    assert "enqueue_sketch_chapters" not in source
    assert "write_manuscript(" not in source
