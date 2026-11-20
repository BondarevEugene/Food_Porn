"""Side-effect-free readiness inspection before Little Legend chapter writing."""
from __future__ import annotations

from app.little_legend.router import StoryDraft
from app.little_legend.story_modes import StoryMode, entry_preflight
from app.little_legend.text_ai_disclosure import (
    configured_text_ai_disclosure,
    consent_allows_provider,
)


def chapter_readiness(draft: StoryDraft) -> dict:
    """Show real queue prerequisites without calling an AI provider."""
    blockers = []
    if draft.parent_sketch is None or draft.graph is None:
        blockers.append("Сначала подготовьте сюжетный план")
    if not draft.outline_approved or not draft.entry.plan_approved:
        blockers.append("Родитель должен утвердить план книги")
    if draft.blueprint is None or not draft.blueprint.family_approved:
        blockers.append("Требуется утверждённый профиль главного героя")
    elif not any(
        item.role == "hero" and item.name == draft.hero
        for item in draft.blueprint.characters
    ):
        blockers.append("Главный герой не совпадает с профилем")
    disclosure = configured_text_ai_disclosure()
    if not disclosure.ready:
        blockers.append("AI-провайдер ещё не настроен для обработки текста")
    elif not consent_allows_provider(draft.text_ai_consent, disclosure):
        blockers.append("Нужно отдельное согласие на обработку текста AI")
    if draft.entry.mode == StoryMode.CLASSIC:
        mode_check = entry_preflight(draft.entry)
        if any("rights" in item.lower() for item in mode_check["blockers"]):
            blockers.append("Не подтверждены права на выбранную версию классики")
    if draft.manuscript is not None and draft.manuscript.parent_approved:
        blockers.append("Рукопись уже утверждена: повторный запуск не нужен")
    return {"ready": not blockers, "blockers": blockers}
