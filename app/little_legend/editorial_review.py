"""Conservative editorial review gates for personalized manuscripts.

Automated checks cannot establish semantic fidelity. Human review is mandatory.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.little_legend.hero_contract import HeroContract, audit_hero_presence
from app.little_legend.story_graph import StoryGraph
from app.little_legend.story_writer import StoryManuscript, manuscript_review


class EditorialDecision(BaseModel):
    hero_fidelity_reviewed: bool = False
    age_appropriateness_reviewed: bool = False
    narrative_continuity_reviewed: bool = False
    parent_final_approval: bool = False
    reviewer_notes: str = Field(default="", max_length=2000)


def editorial_preflight(
    manuscript: StoryManuscript,
    graph: StoryGraph,
    contract: HeroContract,
    decision: EditorialDecision,
) -> dict:
    structural = manuscript_review(manuscript, graph)
    texts = {chapter.scene_id: chapter.text for chapter in manuscript.chapters}
    presence = audit_hero_presence(contract, texts, graph)
    name_matches = manuscript.hero_name == contract.hero_name
    required_reviews = (
        decision.hero_fidelity_reviewed
        and decision.age_appropriateness_reviewed
        and decision.narrative_continuity_reviewed
        and decision.parent_final_approval
    )
    ready = (
        structural["structurally_approved"]
        and contract.family_approved
        and name_matches
        and not presence["missing_text"]
        and not presence["missing_explicit_hero_name"]
        and required_reviews
    )
    return {
        "hero_matches": name_matches,
        "structure": structural,
        "hero_presence": presence,
        "human_reviews_complete": bool(required_reviews),
        "ready_for_print_proof": bool(ready),
        "ready_for_publication": False,
        "semantic_fidelity_automatically_verified": False,
        "editorial_decision": decision.model_dump(mode="json"),
    }
