"""Release UX must reflect persisted production and delivery truth."""
from pathlib import Path

from app.bot.handlers.little_legend_release_preflight import release_issue_hints

ROOT = Path("app/bot/handlers/little_legend.py").read_text(encoding="utf-8")


def test_missing_illustrations_are_not_complete_without_scenes():
    assert 'art_done = readiness.total_scenes > 0 and not any(' in ROOT
    assert 'issue.stage.value == "illustrations"' in ROOT


def test_delivered_book_does_not_offer_resending():
    assert 'status == DeliveryStatus.SENT:' in ROOT
    assert '("✅ Книга уже доставлена", f"ll_release_review:{story_id}")' in ROOT
    assert 'status in (DeliveryStatus.SENDING, DeliveryStatus.UNCERTAIN)' in ROOT
    assert '("📦 Проверить доставку", f"ll_release_review:{story_id}")' in ROOT


def test_approved_art_does_not_disappear_after_pdf_manifest():
    assert "production = await load_owned_production(" in ROOT
    assert "ready_for_assembly = readiness.ready_for_export and status is None" in ROOT


def test_parent_sees_actionable_pdf_blockers_not_internal_codes():
    hints = release_issue_hints([
        "chapter_unapproved", "illustration_incomplete",
        "illustration_incomplete", "editorial_approval_missing",
    ])
    assert hints == [
        "Прочитайте и утвердите главы",
        "Дождитесь завершения иллюстраций",
        "Подтвердите финальную редакторскую проверку",
    ]
    assert release_issue_hints(["unknown_future_code"]) == [
        "Нужна проверка производства",
    ]
