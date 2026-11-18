"""Source-grounded character arc guidance for chapter briefs.

An arc is a plan for fictional story events, not a diagnosis or a claim
about the real child's personality. No AI service is called here.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.little_legend.hero_contract import HeroContract
from app.little_legend.narrative_design import StoryDesign
from app.little_legend.story_graph import StoryGraph


class CharacterArcCheckpoint(BaseModel):
    scene_id: str
    order: int = Field(ge=1)
    beat: str
    narrative_function: str
    approved_goal: str
    approved_consequence: str


class CharacterArcPlan(BaseModel):
    hero_name: str
    desired_outcome: str = ""
    growth_theme: str = ""
    decisive_choice: str = ""
    checkpoints: list[CharacterArcCheckpoint] = Field(default_factory=list)
    missing_anchors: list[str] = Field(default_factory=list)
    family_facts_are_immutable: bool = True
    semantic_arc_verified: bool = False


_BEAT_FUNCTION = {
    "opening": "Show the hero's starting desire through action.",
    "inciting": "Let the hero respond to a change in the familiar world.",
    "ally": "Let the hero form a relationship without losing agency.",
    "clue": "Let the hero notice evidence and revise a hypothesis.",
    "puzzle": "Let the hero try a solution and learn from its outcome.",
    "danger": "Show an age-appropriate choice under pressure.",
    "reversal": "Challenge an earlier assumption without changing family facts.",
    "relationship": "Let relationships change through actions and dialogue.",
    "revelation": "Connect a discovery to clues established earlier.",
    "plan": "Let the hero choose a plan using their own strengths.",
    "climax": "The hero makes the decisive choice; helpers cannot replace them.",
    "resolution": "Show the consequences and emotional closure without a lecture.",
}


def plan_character_arc(
    graph: StoryGraph, contract: HeroContract, design: StoryDesign,
) -> CharacterArcPlan:
    """Prepare explicit, editable arc checkpoints from approved inputs only."""
    if not contract.family_approved:
        raise PermissionError("Parent-approved hero contract required")
    missing = [
        label for label, value in (
            ("desire", design.desire),
            ("transformation", design.transformation),
            ("decisive_choice", design.decisive_choice),
        ) if not value.strip()
    ]
    return CharacterArcPlan(
        hero_name=contract.hero_name,
        desired_outcome=design.desire,
        growth_theme=design.transformation,
        decisive_choice=design.decisive_choice,
        checkpoints=[
            CharacterArcCheckpoint(
                scene_id=node.id, order=node.order, beat=node.beat,
                narrative_function=_BEAT_FUNCTION[node.beat],
                approved_goal=node.goal,
                approved_consequence=node.consequence,
            )
            for node in sorted(graph.nodes, key=lambda item: item.order)
        ],
        missing_anchors=missing,
    )
