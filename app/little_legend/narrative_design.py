"""Age-aware narrative design guidance, without making remote AI calls.

This is an editorial planning assistant, not a generated finished manuscript.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.little_legend.blueprint import BookBlueprint
from app.little_legend.story_graph import StoryGraph

ARC_QUESTIONS = (
    ("Желание", "Чего герой хочет в начале истории?"),
    ("Потребность", "Чему герой должен научиться, чтобы вырасти?"),
    ("Цена ошибки", "Что важное может быть потеряно?"),
    ("Выбор", "Какое решение герой принимает самостоятельно?"),
    ("Перемена", "Чем герой отличается от себя в начале?"),
)
BEAT_GUIDANCE = {
    "opening": "Покажите обычный мир героя и его заветное желание.",
    "inciting": "Добавьте событие, после которого нельзя просто вернуться назад.",
    "ally": "Пусть помощник имеет собственную цель, а не только помогает.",
    "clue": "Улика должна менять представление о загадке.",
    "puzzle": "Подсказку к загадке нужно дать до ответа.",
    "danger": "Опасность должна быть понятной и соразмерной возрасту.",
    "reversal": "Поворот должен переосмысливать уже известные факты.",
    "relationship": "Дайте героям возможность поссориться и помириться.",
    "revelation": "Объяснение тайны должно опираться на ранние детали.",
    "plan": "План должен исходить из сильных сторон ребёнка.",
    "climax": "Ключевой поступок совершает сам главный герой.",
    "resolution": "Покажите последствия выбора и эмоциональное завершение.",
}


class StoryDesign(BaseModel):
    desire: str = Field(default="", max_length=1000)
    need: str = Field(default="", max_length=1000)
    stakes: str = Field(default="", max_length=1000)
    decisive_choice: str = Field(default="", max_length=1000)
    transformation: str = Field(default="", max_length=1000)
    theme: str = Field(default="", max_length=300)
    recurring_symbol: str = Field(default="", max_length=300)
    emotional_safety_note: str = Field(default="", max_length=600)


def design_guidance(
    graph: StoryGraph,
    design: StoryDesign,
    blueprint: BookBlueprint,
) -> dict:
    age = blueprint.controls.age
    if age is None:
        audience = "Возраст не указан: предложите родителю выбрать уровень чтения."
    elif age <= 5:
        audience = "Короткие предложения, повторения, мягкие конфликты и ясная развязка."
    elif age <= 8:
        audience = "Динамичные сцены, конкретные загадки и понятные эмоциональные ставки."
    elif age <= 12:
        audience = "Мотивы второстепенных героев, ложные версии и моральный выбор."
    else:
        audience = "Многослойные мотивы, сложные отношения и неоднозначные решения."
    questions = [
        {"field": field, "label": label, "question": question,
         "filled": bool(getattr(design, field).strip())}
        for (label, question), field in zip(
            ARC_QUESTIONS,
            ("desire", "need", "stakes", "decisive_choice", "transformation"),
            strict=True,
        )
    ]
    scene_advice = [
        {"scene_id": node.id, "order": node.order,
         "beat": node.beat, "tip": BEAT_GUIDANCE[node.beat],
         "locked": node.locked}
        for node in sorted(graph.nodes, key=lambda n: n.order)
    ]
    return {
        "audience_guidance": audience,
        "arc_questions": questions,
        "scene_advice": scene_advice,
        "missing_arc_elements": [item["label"] for item in questions if not item["filled"]],
        "ai_generated": False,
    }
