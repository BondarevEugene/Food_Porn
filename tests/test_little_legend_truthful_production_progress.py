"""Prevent false green ticks in the Little Legend production checklist."""
from pathlib import Path

SOURCE = Path("app/bot/handlers/little_legend.py").read_text(encoding="utf-8")


def test_illustrations_do_not_inherit_pdf_manifest_status():
    assert '("Иллюстрации", art_done, f"ll_art_ready:{story_id}")' in SOURCE
    assert '("Финальная проверка", editorial_done, f"ll_checkpoint:{story_id}")' in SOURCE
    assert 'issue.stage.value == "illustrations"' in SOURCE
    assert "editorial_done = production.editorial_approved" in SOURCE
    assert 'bool(ready_for_assembly or status)' not in SOURCE


def test_manuscript_resumes_review_when_chapters_exist():
    assert (
        'f"ll_manuscript_review:{story_id}" if draft.manuscript is not None '
        'else f"ll_writer_start:{story_id}"'
    ) in SOURCE


def test_no_raw_technical_blockers_on_main_book_screen():
    assert "readiness_message(" not in SOURCE
    assert 'f"{readiness_text}' not in SOURCE


def test_pdf_is_not_marked_complete_without_manifest():
    assert '("Готовый PDF", status is not None, f"ll_release_review:{story_id}")' in SOURCE
