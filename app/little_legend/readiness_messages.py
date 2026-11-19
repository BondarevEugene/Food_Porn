"""Privacy-safe customer-facing explanations of Little Legend readiness blockers."""
from __future__ import annotations

from app.little_legend.production_readiness import ProductionReadiness

MESSAGES = {
    "scenes_missing": ("Додайте сцени", "Добавьте сцены", "Add story scenes"),
    "duplicate_scene_ids": ("Перевірте сцени", "Проверьте сцены", "Review story scenes"),
    "duplicate_chapters": ("Перевірте глави", "Проверьте главы", "Review chapters"),
    "parent_approval_missing": ("Підтвердьте текст", "Утвердите текст", "Approve the manuscript"),
    "hero_missing": ("Додайте героя", "Добавьте героя", "Add a hero"),
    "chapter_missing": ("Допишіть глави", "Завершите главы", "Complete the chapters"),
    "chapter_unapproved": ("Затвердьте глави", "Утвердите главы", "Approve the chapters"),
    "unexpected_chapter": ("Перевірте глави", "Проверьте главы", "Review chapters"),
    "illustration_job_count_invalid": (
        "Перевірте ілюстрації", "Проверьте иллюстрации", "Review illustrations",
    ),
    "illustration_incomplete": (
        "Дочекайтеся ілюстрацій", "Дождитесь иллюстраций", "Wait for illustrations",
    ),
    "illustration_revision_stale": (
        "Оновіть ілюстрації", "Обновите иллюстрации", "Refresh illustrations",
    ),
    "unexpected_illustration": (
        "Перевірте ілюстрації", "Проверьте иллюстрации", "Review illustrations",
    ),
    "editorial_approval_missing": (
        "Завершіть редакторське затвердження",
        "Завершите редакторское утверждение",
        "Complete editorial approval",
    ),
}
UNKNOWN = ("Потрібна перевірка", "Требуется проверка", "Review required")


def readiness_message(report: ProductionReadiness, *, language: str = "en") -> str:
    """Explain blockers without manuscript, child names or illustration content."""
    index = {"uk": 0, "ua": 0, "ru": 1, "en": 2}.get(language, 2)
    if report.ready_for_export:
        return (
            "✅ Книга готова до складання",
            "✅ Книга готова к сборке",
            "✅ Book is ready for assembly",
        )[index]
    heading = (
        "📖 Що залишилося зробити:",
        "📖 Что осталось сделать:",
        "📖 What remains to do:",
    )[index]
    labels = []
    for issue in report.issues:
        if issue.code == "pdf_not_verified":
            continue
        label = MESSAGES.get(issue.code, UNKNOWN)[index]
        if label not in labels:
            labels.append(label)
    return heading + "".join(f"\n• {label}" for label in labels[:8])
