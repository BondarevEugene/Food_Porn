"""Hero-first story contract: preserve the family's original description.

Deterministic preparation and audit only. AI prose generation is a separate
integration; these checks do not claim semantic or emotional correctness.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.little_legend.blueprint import BookBlueprint
from app.little_legend.story_graph import StoryGraph


class FactPriority(StrEnum):
    IMMUTABLE = "immutable"
    IMPORTANT = "important"
    OPTIONAL = "optional"


class HeroFact(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=1200)
    priority: FactPriority = FactPriority.IMPORTANT
    source: str = Field(default="parent_description", max_length=100)


class HeroContract(BaseModel):
    """Source-of-truth facts approved by a parent, not inferred from images."""

    hero_name: str = Field(min_length=1, max_length=100)
    facts: list[HeroFact] = Field(default_factory=list, max_length=80)
    forbidden_inventions: list[str] = Field(default_factory=list, max_length=30)
    family_approved: bool = False

    @model_validator(mode="after")
    def unique_fact_keys(self) -> HeroContract:
        keys = [fact.key for fact in self.facts]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate hero fact keys")
        return self


def contract_from_blueprint(blueprint: BookBlueprint, hero_name: str) -> HeroContract:
    """Copy provided facts verbatim, without inventing a personality or biography."""
    heroes = [item for item in blueprint.characters if item.role == "hero"]
    if len(heroes) != 1 or heroes[0].name.strip().casefold() != hero_name.strip().casefold():
        raise ValueError("Hero name conflicts with the original character profile")
    hero = heroes[0]
    facts = [
        HeroFact(key="name", value=hero.name, priority=FactPriority.IMMUTABLE),
    ]
    for key, value, priority in (
        ("appearance", hero.appearance, FactPriority.IMMUTABLE),
        ("mannerisms", hero.mannerisms, FactPriority.IMPORTANT),
        ("favorite_phrases", hero.favorite_phrases, FactPriority.IMPORTANT),
        ("relationship", hero.relationship, FactPriority.IMPORTANT),
        ("visual_identity_notes", hero.visual_identity_notes, FactPriority.IMMUTABLE),
    ):
        if value.strip():
            facts.append(HeroFact(key=key, value=value.strip(), priority=priority))
    if blueprint.controls.age is not None:
        facts.append(HeroFact(
            key="age", value=str(blueprint.controls.age),
            priority=FactPriority.IMMUTABLE,
        ))
    return HeroContract(
        hero_name=hero.name,
        facts=facts,
        forbidden_inventions=[
            "Не менять имя, возраст, внешность и семейные отношения героя",
            "Не приписывать ребёнку травмы, диагнозы, страхи или недостатки",
            "Не заменять главного героя другим персонажем",
            "Не изображать неподтверждённые детали как реальные факты о ребёнке",
        ],
        family_approved=blueprint.family_approved,
    )


def scene_directives(contract: HeroContract, graph: StoryGraph) -> list[dict]:
    """Give every scene the same canonical hero facts and agency requirement."""
    immutable = [fact.model_dump() for fact in contract.facts
                 if fact.priority == FactPriority.IMMUTABLE]
    important = [fact.model_dump() for fact in contract.facts
                 if fact.priority == FactPriority.IMPORTANT]
    return [
        {
            "scene_id": node.id,
            "hero": contract.hero_name,
            "immutable_facts": immutable,
            "important_facts": important,
            "forbidden_inventions": contract.forbidden_inventions,
            "agency_rule": (
                "Герой влияет на исход сцены собственным выбором; "
                "помощники не решают за него главную задачу."
            ),
            "scene_goal": node.goal,
            "scene_conflict": node.conflict,
            "scene_consequence": node.consequence,
        }
        for node in sorted(graph.nodes, key=lambda item: item.order)
    ]


def audit_hero_presence(
    contract: HeroContract, scene_texts: dict[str, str], graph: StoryGraph
) -> dict:
    """Literal name/presence checks only; require human semantic review.

    Name inflections and synonyms may cause false negatives. A name mention
    alone never proves faithful characterization.
    """
    findings = []
    for node in sorted(graph.nodes, key=lambda item: item.order):
        text = scene_texts.get(node.id, "")
        name_present = contract.hero_name.casefold() in text.casefold()
        findings.append({
            "scene_id": node.id,
            "text_present": bool(text.strip()),
            "hero_name_mentioned": name_present,
            "requires_semantic_review": True,
        })
    return {
        "hero": contract.hero_name,
        "family_approved": contract.family_approved,
        "scenes": findings,
        "missing_text": [f["scene_id"] for f in findings if not f["text_present"]],
        "missing_explicit_hero_name": [
            f["scene_id"] for f in findings if not f["hero_name_mentioned"]
        ],
        "character_fidelity_verified": False,
        "ready_for_publication": False,
    }


def hero_writing_brief(
    contract: HeroContract, blueprint: BookBlueprint
) -> dict:
    """Structured model input; never sends data to an external provider."""
    return {
        "language": blueprint.controls.language,
        "age": blueprint.controls.age,
        "tone": blueprint.controls.tone,
        "reading_level": blueprint.controls.reading_level,
        "narrative_person": blueprint.controls.narrative_person,
        "hero": contract.model_dump(mode="json"),
        "instructions": [
            "Главный герой — именно описанный ребёнок, не абстрактный персонаж.",
            "Сохраняй все immutable-факты без исключений.",
            "Встраивай привычки, любимые фразы и отношения в действия и диалоги, "
            "а не просто перечисляй их.",
            "Каждая сцена должна раскрывать характер героя через поступки.",
            "Не выдумывай биографические сведения о реальном ребёнке.",
            "Пусть герой принимает ключевые решения сам, с поддержкой близких.",
            "Сохраняй преемственность событий и черт во всех главах.",
            "Если исходных данных недостаточно, оставляй деталь неопределённой.",
        ],
        "approved_for_generation": contract.family_approved,
        "remote_generation_performed": False,
    }
