"""Telegram writing launch must delegate to atomic server-side queue checks."""
from pathlib import Path

from app.bot.handlers.little_legend_outline import _keyboard


def test_writer_buttons_are_present():
    markup = _keyboard(42, approvable=False)
    values = [
        button.callback_data
        for row in markup.inline_keyboard for button in row
    ]
    assert "ll_writer_status:42" in values
    assert "ll_writer_ready:42" in values


def test_enqueue_rechecks_readiness_inside_story_lock():
    source = Path("app/little_legend/sketch_enqueue.py").read_text(
        encoding="utf-8",
    )
    assert "with_for_update()" in source
    assert "chapter_readiness(draft)" in source
    assert "if not readiness[\"ready\"]:" in source
    assert 'JobStatus.QUEUED.value' in source


def test_confirmation_uses_owner_scoped_queue_not_direct_ai():
    source = Path("app/bot/handlers/little_legend_outline.py").read_text(
        encoding="utf-8",
    )
    assert "ll_writer_confirm:" in source
    assert "enqueue_sketch_chapters(" in source
    assert "owner_id=callback.from_user.id" in source
    assert "await session.commit()" not in source.split(
        "async def confirm_writer_launch", 1,
    )[1].split("async def writer_job_status", 1)[0]
