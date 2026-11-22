"""Editorial approval is a real owner-scoped stage, not a fake green tick."""
from pathlib import Path

ROOT = Path("app/bot/handlers/little_legend.py").read_text(encoding="utf-8")
EDITORIAL = Path("app/bot/handlers/little_legend_editorial.py").read_text(
    encoding="utf-8",
)


def test_editorial_step_has_real_telegram_route():
    assert '("Финальная проверка", editorial_done, f"ll_editorial:{story_id}")' in ROOT
    assert "router.include_router(editorial_router)" in ROOT
    assert 'F.data.startswith("ll_editorial:")' in EDITORIAL


def test_approval_requires_owner_and_complete_manuscript():
    assert "callback.message.chat.id == callback.from_user.id" in EDITORIAL
    assert "stories.c.owner_id == callback.from_user.id" in EDITORIAL
    assert "with_for_update()" in EDITORIAL
    assert "manuscript_review(draft.manuscript, draft.graph)" in EDITORIAL
    assert '["structurally_approved"]' in EDITORIAL
    assert "if not editorial_ready(draft):" in EDITORIAL


def test_final_review_requires_explicit_parent_action():
    assert 'f"ll_editorial_accept:{story_id}"' in EDITORIAL
    assert "hero_fidelity_reviewed=True" in EDITORIAL
    assert "age_appropriateness_reviewed=True" in EDITORIAL
    assert "narrative_continuity_reviewed=True" in EDITORIAL
    assert "parent_final_approval=True" in EDITORIAL
    assert "await session.commit()" in EDITORIAL
    assert "enqueue_illustration_jobs(" not in EDITORIAL
    assert "prepare_owned_release(" not in EDITORIAL
