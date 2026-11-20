"""Little Legend production checkpoint does not confuse queued jobs with books."""
from app.bot.handlers.little_legend_checkpoint import checkpoint_summary
from app.little_legend.router import StoryDraft


def test_empty_checkpoint_is_not_a_finished_book():
    message = checkpoint_summary(StoryDraft(), [], [])
    assert "Главы сохранены: 0/0" in message
    assert "создать сюжетный план" in message
    assert "готово к сборке" not in message


def test_queued_writer_job_does_not_count_as_saved_chapter():
    message = checkpoint_summary(StoryDraft(), ["queued", "running"], [])
    assert "Главы сохранены: 0/0" in message
    assert "queued: 1" in message
    assert "running: 1" in message
