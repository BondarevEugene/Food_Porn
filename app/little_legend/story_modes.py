"""Validated entry modes for Little Legend; no external AI calls or photo storage."""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.little_legend.client_sketch import ParentSketch, SketchOutline, outline_from_sketch


class StoryMode(StrEnum):
    DIRECTOR = "director"
    CLASSIC = "classic"
    BRIEF = "brief"


class ClassicSource(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    original_hero: str = Field(min_length=1, max_length=100)
    child_hero: str = Field(min_length=1, max_length=100)
    source_version: str = Field(default="", max_length=300)
    public_domain_verified: bool = False
    verification_note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_rights(self) -> ClassicSource:
        if self.public_domain_verified and not self.verification_note.strip():
            raise ValueError("Verified public-domain status requires evidence")
        return self


class SimpleBrief(BaseModel):
    child_hero: str = Field(min_length=1, max_length=100)
    characters: list[str] = Field(min_length=1, max_length=20)
    events: list[str] = Field(min_length=1, max_length=12)
    moral: str = Field(default="", max_length=1000)
    exclusions: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def nonempty(self) -> SimpleBrief:
        if not all(x.strip() for x in self.characters + self.events):
            raise ValueError("Characters and events cannot be blank")
        return self


class StoryEntry(BaseModel):
    mode: StoryMode = StoryMode.DIRECTOR
    classic: ClassicSource | None = None
    brief: SimpleBrief | None = None
    photo_reference_ids: list[str] = Field(default_factory=list, max_length=20)
    photo_consent_confirmed: bool = False
    plan_approved: bool = False

    @model_validator(mode="after")
    def matching_payload(self) -> StoryEntry:
        if self.mode == StoryMode.CLASSIC and self.classic is None:
            raise ValueError("Classic mode requires classic source")
        if self.mode == StoryMode.BRIEF and self.brief is None:
            raise ValueError("Brief mode requires a brief")
        if self.mode != StoryMode.CLASSIC and self.classic is not None:
            raise ValueError("Classic source is only valid in classic mode")
        if self.mode != StoryMode.BRIEF and self.brief is not None:
            raise ValueError("Brief is only valid in brief mode")
        if self.photo_reference_ids and not self.photo_consent_confirmed:
            raise ValueError("Photo references require parental consent")
        return self


def entry_preflight(entry: StoryEntry) -> dict:
    """Fail closed: classic source rights and parental plan approval are mandatory."""
    blockers = []
    if entry.mode == StoryMode.CLASSIC:
        assert entry.classic is not None
        if not entry.classic.public_domain_verified:
            blockers.append("Source rights have not been verified")
    if not entry.plan_approved:
        blockers.append("Parent has not approved the story plan")
    return {"ready": not blockers, "blockers": blockers, "mode": entry.mode.value}


def brief_parent_sketch(brief: SimpleBrief) -> ParentSketch:
    """Persist the exact parental source used by the approved writer pipeline."""
    premise = (
        f"Главный герой: {brief.child_hero}. "
        f"Другие персонажи: {', '.join(brief.characters)}."
    )
    return ParentSketch(
        premise=premise,
        moments=brief.events,
        lesson=brief.moral,
        avoid=brief.exclusions,
    )


def brief_outline(brief: SimpleBrief, *, chapter_count: int = 12) -> SketchOutline:
    """Reuse the existing source-only outline engine, without inventing events."""
    return outline_from_sketch(brief_parent_sketch(brief), chapter_count=chapter_count)


def classic_adaptation_brief(source: ClassicSource) -> dict:
    """Return editorial constraints, never copyrighted source text."""
    return {
        "title": source.title,
        "replacement": {"from": source.original_hero, "to": source.child_hero},
        "source_version": source.source_version,
        "instructions": (
            "Write a new child-safe adaptation based only on verified permitted "
            "source material. Preserve plot causality, update all pronouns and "
            "relationships, and never reproduce an unverified translation."
        ),
        "rights_verified": source.public_domain_verified,
    }
