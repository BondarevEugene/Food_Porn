"""Telegram book creation follows saved parental authorization and queue gates."""
from pathlib import Path

from app.little_legend.consent import ConsentDecision, ConsentRecord, record_decision

ROOT = Path("app/bot/handlers/little_legend.py").read_text(encoding="utf-8")
FLOW = Path("app/bot/handlers/little_legend_writer_start.py").read_text(
    encoding="utf-8",
)


def test_required_steps_have_actual_actions():
    assert '("Условия и полномочия родителя", terms_done, f"ll_terms:{story_id}")' in ROOT
    assert (
        'f"ll_manuscript_review:{story_id}" if draft.manuscript is not None '
        'else f"ll_writer_start:{story_id}"'
    ) in ROOT
    assert "router.include_router(writer_start_router)" in ROOT


def test_terms_do_not_imply_photo_permission():
    record = record_decision(
        ConsentRecord(),
        ConsentDecision(accept_terms=True, declare_parental_authority=True),
    )
    assert record.terms_accepted_at is not None
    assert not record.photo_consent_active


def test_telegram_launch_is_explicit_and_owner_scoped():
    assert 'callback_data=f"ll_writer_confirm:{story_id}"' not in FLOW
    assert 'f"ll_writer_confirm:{story_id}"' in FLOW
    assert "chapter_readiness(draft)" in FLOW
    assert "consent_status(draft.consent)" in FLOW
    assert "enqueue_sketch_chapters(" in FLOW
    assert "owner_id=callback.from_user.id" in FLOW
    assert "with_for_update()" in FLOW
    assert "await session.commit()" in FLOW
