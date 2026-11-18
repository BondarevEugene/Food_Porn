"""Turn a parent's raw story sketches into an editable narrative blueprint.

All supplied ideas remain source material. This module never invents facts
about a real child or sends their description to an external service.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, model_validator

from app.little_legend.narrative_design import StoryDesign
from app.little_legend.story_graph import BEATS, QUESTIONS, StoryGraph, build_graph


class ParentSketch(BaseModel):
    premise: str = Field(min_length=10, max_length=4000)
    moments: list[str] = Field(min_length=1, max_length=20)
    wish: str = Field(default="", max_length=1000)
    challenge: str = Field(default="", max_length=1000)
    special_choice: str = Field(default="", max_length=1000)
    ending: str = Field(default="", max_length=1000)
    lesson: str = Field(default="", max_length=1000)
    avoid: list[str] = Field(default_factory=list, max_length=20)
    relationships: str = Field(default="", max_length=1200)
    emotional_safety: str = Field(default="", max_length=600)

    @model_validator(mode="after")
    def require_real_moments(self) -> ParentSketch:
        if not any(moment.strip() for moment in self.moments):
            raise ValueError("At least one nonempty story moment is required")
        return self


class SketchOutline(BaseModel):
    graph: StoryGraph
    design: StoryDesign
    source_moments: list[str]
    unresolved_questions: list[str]
    source_only: bool = True
    ai_generated: bool = False


def _sentences(text: str) -> list[str]:
    return [
        part.strip(" \t\r\n-•")
        for part in re.split(r"(?<=[.!?])\s+|\n+", text)
        if part.strip(" \t\r\n-•")
    ]


def outline_from_sketch(sketch: ParentSketch, *, chapter_count: int = 12) -> SketchOutline:
    """Spread original moments across story beats without fabricating events."""
    if not 3 <= chapter_count <= 12:
        raise ValueError("Chapter count must be between 3 and 12")
    moments = [
        sentence
        for item in sketch.moments
        for sentence in _sentences(item)
    ]
    if not moments:
        raise ValueError("Sketch has no usable moments")
    if len(moments) > chapter_count:
        raise ValueError("Too many distinct moments: merge some before planning")
    summaries = [""] * chapter_count
    for index, moment in enumerate(moments):
        slot = index * (chapter_count - 1) // max(1, len(moments) - 1)
        if summaries[slot]:
            summaries[slot] += " " + moment
        else:
            summaries[slot] = moment
    summaries[0] = (sketch.premise.strip() + " " + summaries[0]).strip()
    if sketch.ending.strip():
        summaries[-1] = (summaries[-1] + " " + sketch.ending.strip()).strip()
    graph = build_graph(summaries)
    for node in graph.nodes:
        beat_index = min((node.order - 1) * len(BEATS) // chapter_count, 11)
        node.title = QUESTIONS[beat_index]
        node.goal = QUESTIONS[beat_index]
        if node.beat == "climax" and sketch.special_choice.strip():
            node.goal = sketch.special_choice.strip()
        if node.beat == "danger" and sketch.challenge.strip():
            node.conflict = sketch.challenge.strip()
    design = StoryDesign(
        desire=sketch.wish.strip(),
        need=sketch.lesson.strip(),
        stakes=sketch.challenge.strip(),
        decisive_choice=sketch.special_choice.strip(),
        transformation=sketch.ending.strip(),
        theme=sketch.lesson.strip()[:300],
        emotional_safety_note=sketch.emotional_safety.strip(),
    )
    questions = []
    if not sketch.wish.strip():
        questions.append("Чего герой хочет больше всего?")
    if not sketch.special_choice.strip():
        questions.append("Какой решающий выбор ребёнок сделает сам?")
    if not sketch.ending.strip():
        questions.append("Как родитель видит счастливую развязку?")
    if not sketch.relationships.strip():
        questions.append("Кто из близких участвует в приключении?")
    if not sketch.emotional_safety.strip():
        questions.append("Какие темы и страхи лучше исключить?")
    questions.extend(
        f"Что должно произойти в главе {node.order}?"
        for node in graph.nodes if not node.summary
    )
    return SketchOutline(
        graph=graph,
        design=design,
        source_moments=moments,
        unresolved_questions=questions,
    )
