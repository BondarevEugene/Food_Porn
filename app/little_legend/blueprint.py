"""Little Legend creative controls: every subsystem has quick and director modes.

Character likeness requires explicit parental consent and a reviewed visual
reference. No child photos are uploaded or persisted by this module.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ControlMode(StrEnum):
    QUICK = "quick"
    DIRECTOR = "director"


class CreativeControls(BaseModel):
    mode: ControlMode = ControlMode.QUICK
    age: int | None = Field(default=None, ge=0, le=17)
    tone: Literal["gentle", "balanced", "epic"] = "balanced"
    creative_freedom: Literal["strict", "balanced", "creative"] = "balanced"
    story_length: Literal["short", "standard", "long"] = "standard"
    narrative_person: Literal["third", "second"] = "third"
    riddles: int = Field(default=2, ge=0, le=8)
    reading_level: Literal["early", "independent", "family"] = "family"
    illustration_style: Literal[
        "watercolor", "storybook", "cinematic", "pencil", "gouache"
    ] = "storybook"
    print_format: Literal["A5", "A4", "210x210"] = "A5"
    language: Literal["ru", "uk", "en"] = "ru"
    protected_plot_points: list[str] = Field(default_factory=list, max_length=12)


class CharacterProfile(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: Literal["hero", "friend", "family", "pet", "other"] = "hero"
    appearance: str = Field(default="", max_length=1200)
    mannerisms: str = Field(default="", max_length=1200)
    favorite_phrases: str = Field(default="", max_length=1000)
    relationship: str = Field(default="", max_length=400)
    visual_identity_notes: str = Field(default="", max_length=1200)
    photo_consent_confirmed: bool = False
    visual_reference_approved: bool = False
    # Never store image bytes, URLs, or face embeddings in story JSON.


class PublishingControls(BaseModel):
    mode: ControlMode = ControlMode.QUICK
    trim_size: Literal["A5", "A4", "210x210"] = "A5"
    bleed_mm: float = Field(default=3, ge=0, le=10)
    safe_margin_mm: float = Field(default=12, ge=8, le=35)
    target_dpi: int = Field(default=300, ge=150, le=600)
    edition: str = Field(default="Первое", max_length=100)
    imprint: str = Field(default="", max_length=120)
    city: str = Field(default="", max_length=120)
    author_credit: str = Field(default="", max_length=160)
    illustrator_credit: str = Field(default="", max_length=160)
    copy_number: str = Field(default="", max_length=60)
    color_profile: Literal["printer_spec_required", "RGB_proof"] = "printer_spec_required"


class BookBlueprint(BaseModel):
    controls: CreativeControls = Field(default_factory=CreativeControls)
    publishing: PublishingControls = Field(default_factory=PublishingControls)
    characters: list[CharacterProfile] = Field(default_factory=list, max_length=30)
    family_approved: bool = False

    @model_validator(mode="after")
    def unique_heroes(self) -> BookBlueprint:
        if sum(character.role == "hero" for character in self.characters) > 1:
            raise ValueError("Only one primary hero is supported")
        return self


def quick_blueprint(hero: str, age: int | None = None) -> BookBlueprint:
    return BookBlueprint(
        controls=CreativeControls(age=age),
        characters=[CharacterProfile(name=hero)],
    )


def visual_consistency_check(blueprint: BookBlueprint) -> dict:
    """Gate illustration generation until visual references are approved.

    A descriptive profile can be used without photos. Photo likeness cannot
    be promised or measured without approved source images and human review.
    """
    checks = []
    for character in blueprint.characters:
        if character.role != "hero":
            continue
        checks.append({
            "character": character.name,
            "description_present": bool(character.appearance.strip()),
            "visual_reference_approved": character.visual_reference_approved,
            "photo_consent_confirmed": character.photo_consent_confirmed,
            "photo_likeness_ready": (
                character.photo_consent_confirmed
                and character.visual_reference_approved
            ),
        })
    return {"characters": checks, "photo_processing_enabled": False}


def print_preflight(
    publishing: PublishingControls,
    *, illustrations: list[dict] | None = None,
    final_prose_approved: bool = False,
) -> dict:
    """Conservative production gate; metadata is not evidence of press readiness."""
    problems = []
    if not final_prose_approved:
        problems.append("Full manuscript has not been editorially approved")
    if publishing.color_profile == "printer_spec_required":
        problems.append("Printer color profile and output intent not specified")
    if not illustrations:
        problems.append("Final illustrations are missing")
    else:
        for index, illustration in enumerate(illustrations, 1):
            if int(illustration.get("effective_dpi", 0)) < publishing.target_dpi:
                problems.append(f"Illustration {index}: insufficient effective DPI")
            if not illustration.get("bleed_checked"):
                problems.append(f"Illustration {index}: bleed not checked")
    if not publishing.author_credit.strip():
        problems.append("Author credit must be reviewed")
    if not publishing.illustrator_credit.strip():
        problems.append("Illustrator credit must be reviewed")
    return {
        "ready_for_press": not problems,
        "problems": problems,
        "proof_only": bool(problems),
    }
