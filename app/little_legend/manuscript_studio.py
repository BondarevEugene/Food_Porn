"""Text-only personalized story planning with immutable hero continuity.

No remote AI calls or child-photo processing occur here.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.little_legend.blueprint import BookBlueprint
from app.little_legend.hero_contract import HeroContract, hero_writing_brief
from app.little_legend.narrative_design import StoryDesign
from app.little_legend.story_graph import StoryGraph


class ChapterPlan(BaseModel):
    scene_id: str
    title: str = Field(min_length=1, max_length=160)
    hero_action: str = Field(min_length=1, max_length=1200)
    character_detail: str = Field(min_length=1, max_length=1200)
    emotional_change: str = Field(min_length=1, max_length=1200)
    causal_link: str = Field(min_length=1, max_length=1200)
    manuscript: str = Field(default="", max_length=20000)
    parent_approved: bool = False


class ManuscriptPlan(BaseModel):
    hero_name: str
    chapters: list[ChapterPlan] = Field(min_length=1, max_length=40)
    parent_approved: bool = False

    @model_validator(mode="after")
    def unique_chapters(self) -> ManuscriptPlan:
        ids = [chapter.scene_id for chapter in self.chapters]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate chapter scene identifiers")
        return self


def manuscript_preflight(
    plan: ManuscriptPlan, graph: StoryGraph, contract: HeroContract,
) -> dict:
    """Block publication unless every scene is present and approved."""
    expected = {node.id for node in graph.nodes}
    actual = {chapter.scene_id for chapter in plan.chapters}
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    incomplete = [
        chapter.scene_id for chapter in plan.chapters
        if not chapter.manuscript.strip()
    ]
    unapproved = [
        chapter.scene_id for chapter in plan.chapters
        if not chapter.parent_approved
    ]
    hero_matches = plan.hero_name == contract.hero_name
    ready = (
        hero_matches and not missing and not unexpected
        and not incomplete and not unapproved
        and plan.parent_approved and contract.family_approved
    )
    return {
        "hero_matches": hero_matches,
        "missing_scenes": missing,
        "unexpected_scenes": unexpected,
        "empty_manuscripts": incomplete,
        "unapproved_scenes": unapproved,
        "family_approved": contract.family_approved,
        "ready_for_editorial_review": ready,
        "ready_for_publication": False,
        "semantic_fidelity_verified": False,
    }


def chapter_writing_jobs(
    graph: StoryGraph, contract: HeroContract, blueprint: BookBlueprint,
    design: StoryDesign,
) -> list[dict]:
    """Prepare independently editable chapter jobs with a common hero bible."""
    brief = hero_writing_brief(contract, blueprint)
    ordered = sorted(graph.nodes, key=lambda node: node.order)
    return [
        {
            "scene_id": node.id,
            "chapter": node.order,
            "beat": node.beat,
            "act": node.act,
            "title": node.title,
            "story_context": {
                "desire": design.desire,
                "need": design.need,
                "stakes": design.stakes,
                "theme": design.theme,
                "decisive_choice": design.decisive_choice,
                "transformation": design.transformation,
                "setup": ordered[0].summary,
                "previous_scene": ordered[i - 1].summary if i else "",
                "current_scene": node.summary,
                "next_scene": ordered[i + 1].summary if i + 1 < len(ordered) else "",
                "goal": node.goal,
                "conflict": node.conflict,
                "consequence": node.consequence,
            },
            "hero_brief": brief,
            "instructions": [
                "Герой совершает поступки в соответствии с исходным описанием.",
                "Упоминай особенности героя органично, не списком.",
                "Не меняй факты о ребёнке и не выдумывай его биографию.",
                "Сохраняй причинно-следственную связь с соседними главами.",
                "Кульминационное решение принимает сам ребёнок-герой.",
                "Пиши литературно, с учётом возраста и выбранного языка.",
            ],
            "remote_generation_performed": False,
        }
        for i, node in enumerate(ordered)
    ]
