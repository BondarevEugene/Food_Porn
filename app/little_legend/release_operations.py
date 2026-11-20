"""Privacy-safe operational presentation for Little Legend release audits.

Pure functions: no storage writes, billing, queue dispatch or network calls.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.little_legend.release_decision import decide_release
from app.little_legend.release_quality_engine import ReleaseAudit

Severity = Literal["info", "warning", "error"]

ISSUE_CATALOG: dict[str, tuple[str, Severity, str]] = {
    "low_resolution_illustrations": (
        "Недостаточное разрешение", "warning",
        "Проверьте качество иллюстраций для печати; цифровая версия может быть доступна.",
    ),
    "illustration_below_300_dpi": (
        "Низкий DPI", "warning", "Замените иллюстрацию на изображение большего разрешения.",
    ),
    "paid_delivery_gate_failed": (
        "Проверка выдачи не пройдена", "error",
        "Проверьте обложку, посвящение, главы и отсутствие редакционных пометок.",
    ),
    "chapter_art_missing": (
        "Иллюстрации глав отсутствуют", "error",
        "Проверьте утверждённые изображения для каждой главы.",
    ),
    "illustrations_missing": (
        "Иллюстрации отсутствуют", "error",
        "Подготовьте и утвердите изображения перед выпуском.",
    ),
    "insufficient_pages": (
        "Недостаточно страниц", "error",
        "Пересоберите книгу после проверки полноты глав.",
    ),
    "pdf_content_unreadable": (
        "Не удалось прочитать PDF", "error",
        "Проверьте корректность сформированного файла.",
    ),
    "blank_or_image_only_page": (
        "Пустая страница", "error",
        "Проверьте текстовое наполнение и верстку страниц.",
    ),
    "editorial_proof_not_deliverable": (
        "Редакторский макет", "error",
        "Для клиента требуется отдельная цифровая редакция.",
    ),
}


class ReleaseIssueView(BaseModel):
    code: str
    title: str
    severity: Severity
    action: str


class ReleaseOperationsView(BaseModel):
    status: Literal["ready", "needs_correction", "blocked"]
    can_deliver: bool
    can_recheck_without_payment: bool
    edition: Literal["digital", "editorial_proof"]
    page_count: int = Field(ge=0)
    expected_scenes: int = Field(ge=1)
    illustration_count: int = Field(ge=0)
    print_ready: bool = False
    issues: list[ReleaseIssueView] = Field(default_factory=list)


def present_release_audit(audit: ReleaseAudit) -> ReleaseOperationsView:
    """Build a bounded operator view without any personal story content."""
    decision = decide_release(audit)
    issues = []
    for code in dict.fromkeys(audit.issue_codes):
        title, severity, action = ISSUE_CATALOG.get(
            code, ("Неизвестная проблема", "error", "Проверьте журнал выпуска."),
        )
        issues.append(ReleaseIssueView(
            code=code, title=title, severity=severity, action=action,
        ))
    return ReleaseOperationsView(
        status=decision.status,
        can_deliver=decision.can_deliver,
        can_recheck_without_payment=decision.retry_allowed,
        edition=audit.edition,
        page_count=audit.page_count,
        expected_scenes=audit.expected_scenes,
        illustration_count=audit.illustration_count,
        print_ready=False,
        issues=issues,
    )
