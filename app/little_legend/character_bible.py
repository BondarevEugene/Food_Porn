"""Approved character bible and repeatable scene art briefs.

Never infer child appearance from a photograph or invent missing traits.
This module prepares provider-independent data; it never dispatches paid AI.
"""
from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field

from app.little_legend.blueprint import BookBlueprint
from app.little_legend.hero_contract import HeroContract
from app.little_legend.story_graph import StoryGraph


class CharacterIdentity(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: str
    appearance: str = ""
    visual_identity_notes: str = ""
    relationship: str = ""


class CharacterBible(BaseModel):
    style: str
    language: str
    characters: list[CharacterIdentity]
    immutable_hero_facts: dict[str, str]
    forbidden_inventions: list[str]
    fingerprint: str


class SceneArtBrief(BaseModel):
    scene_id: str
    scene_order: int
    title: str
    summary: str
    illustration_prompt: str
    style: str
    language: str
    character_bible_fingerprint: str
    characters: list[CharacterIdentity]
    immutable_hero_facts: dict[str, str]
    forbidden_inventions: list[str]
    requirements: list[str]


def build_character_bible(
    blueprint: BookBlueprint,
    contract: HeroContract,
) -> CharacterBible:
    """Require family approval and canonical hero identity."""
    if not blueprint.family_approved or not contract.family_approved:
        raise PermissionError("Family-approved character profiles are required")
    heroes = [item for item in blueprint.characters if item.role == "hero"]
    if len(heroes) != 1 or heroes[0].name != contract.hero_name:
        raise ValueError("Character bible hero must match approved contract")
    characters = [
        CharacterIdentity(
            name=item.name,
            role=item.role,
            appearance=item.appearance.strip(),
            visual_identity_notes=item.visual_identity_notes.strip(),
            relationship=item.relationship.strip(),
        )
        for item in blueprint.characters
    ]
    facts = {
        fact.key: fact.value
        for fact in contract.facts
        if fact.priority == "immutable"
    }
    if facts.get("name", contract.hero_name) != contract.hero_name:
        raise ValueError("Immutable hero name conflicts with approved hero")
    canonical = {
        "style": blueprint.controls.illustration_style,
        "language": blueprint.controls.language,
        "characters": [item.model_dump(mode="json") for item in characters],
        "immutable_hero_facts": facts,
        "forbidden_inventions": contract.forbidden_inventions,
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            canonical, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return CharacterBible(**canonical, fingerprint=fingerprint)


def scene_art_briefs(
    graph: StoryGraph,
    bible: CharacterBible,
) -> list[SceneArtBrief]:
    """Repeat the same approved visual identity across all scene briefs."""
    return [
        SceneArtBrief(
            scene_id=node.id,
            scene_order=node.order,
            title=node.title,
            summary=node.summary,
            illustration_prompt=node.illustration_prompt,
            style=bible.style,
            language=bible.language,
            character_bible_fingerprint=bible.fingerprint,
            characters=[character.model_copy(deep=True)
                        for character in bible.characters],
            immutable_hero_facts=dict(bible.immutable_hero_facts),
            forbidden_inventions=list(bible.forbidden_inventions),
            requirements=[
                "Maintain the approved character appearance across all scenes",
                "Do not invent personal details about a real child",
                "Do not infer appearance from photographs",
                "Preserve the selected illustration style throughout the book",
                "Keep important faces and features away from page trim",
                "Human visual review is required before release",
            ],
        )
        for node in sorted(graph.nodes, key=lambda item: item.order)
    ]


def audit_scene_art_briefs(
    briefs: list[SceneArtBrief],
    bible: CharacterBible,
) -> list[str]:
    """Reject missing, duplicated or inconsistent scene art instructions."""
    issues = []
    scene_ids = [brief.scene_id for brief in briefs]
    if len(scene_ids) != len(set(scene_ids)):
        issues.append("duplicate_scene_ids")
    for brief in briefs:
        if brief.character_bible_fingerprint != bible.fingerprint:
            issues.append(f"{brief.scene_id}:bible_fingerprint_mismatch")
        if brief.style != bible.style or brief.language != bible.language:
            issues.append(f"{brief.scene_id}:style_or_language_mismatch")
        if brief.characters != bible.characters:
            issues.append(f"{brief.scene_id}:character_identity_mismatch")
        if brief.immutable_hero_facts != bible.immutable_hero_facts:
            issues.append(f"{brief.scene_id}:hero_facts_mismatch")
        if brief.forbidden_inventions != bible.forbidden_inventions:
            issues.append(f"{brief.scene_id}:forbidden_inventions_mismatch")
    return issues
