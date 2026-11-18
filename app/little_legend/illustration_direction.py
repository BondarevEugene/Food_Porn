"""Illustration direction contracts with stable character identity anchors.

This module prepares prompts only; it does not upload photos or invoke image
generation. An approved portrait workflow must precede photo-based likeness.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.little_legend.blueprint import BookBlueprint
from app.little_legend.story_graph import SceneNode


class IllustrationBrief(BaseModel):
    scene_id: str
    prompt: str = Field(max_length=6000)
    negative_constraints: list[str]
    reference_approval_required: bool = True
    generation_enabled: bool = False


def build_illustration_brief(
    scene: SceneNode,
    blueprint: BookBlueprint,
    *,
    hero: str,
) -> IllustrationBrief:
    controls = blueprint.controls
    identity = next(
        (person for person in blueprint.characters if person.role == "hero"),
        None,
    )
    notes = []
    if identity is not None:
        if identity.appearance.strip():
            notes.append("Внешность: " + identity.appearance.strip())
        if identity.visual_identity_notes.strip():
            notes.append("Постоянные приметы: " + identity.visual_identity_notes.strip())
    return IllustrationBrief(
        scene_id=scene.id,
        prompt="\n".join([
            "Оригинальная иллюстрация для персональной детской книги.",
            f"Главный герой: {hero}.",
            f"Стиль: {controls.illustration_style}.",
            f"Возраст героя: {controls.age if controls.age is not None else 'не указан'}.",
            f"Сцена: {scene.summary}.",
            f"Композиция: {scene.illustration_prompt or 'Книжный разворот, место для текста.'}",
            *notes,
            "Сохранять одни и те же черты лица, волосы, пропорции и приметы во всех сценах.",
            "Не воспроизводить защищённых персонажей других произведений.",
        ]),
        negative_constraints=[
            "Изменение возраста и внешности между страницами",
            "Лишние пальцы или конечности",
            "Текст, логотипы и водяные знаки на изображении",
            "Обрезанные лица и важные детали в зоне переплёта",
        ],
        reference_approval_required=True,
        generation_enabled=False,
    )
