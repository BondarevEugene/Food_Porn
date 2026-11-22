"""Telegram text AI consent must be separate, explicit and owner-scoped."""
from pathlib import Path

SOURCE = Path("app/bot/handlers/little_legend.py").read_text(encoding="utf-8")


def test_text_consent_is_a_real_checklist_stage():
    assert '("Согласие на AI-текст", ai_done, f"ll_text_notice:{story_id}")' in SOURCE
    assert "consent_allows_provider(draft.text_ai_consent, disclosure)" in SOURCE


def test_acceptance_requires_existing_terms_and_owner():
    section = SOURCE.split("async def little_legend_text_accept", 1)[1].split(
        '@router.callback_query(F.data.startswith("ll_book_tools:"))', 1,
    )[0]
    assert "stories.c.owner_id == callback.from_user.id" in section
    assert "with_for_update()" in section
    assert "accept_server_disclosure(" in section
    assert "terms_accepted=terms_accepted" in section
    assert "await session.commit()" in section
    assert "enqueue_sketch_chapters(" not in section


def test_notice_does_not_send_child_photos():
    section = SOURCE.split("async def little_legend_text_notice", 1)[1].split(
        "async def little_legend_text_accept", 1,
    )[0]
    assert "disclosure.notice()" in section
    assert "Фотографии не передаются" in section
    assert "ll_text_accept:" in section
