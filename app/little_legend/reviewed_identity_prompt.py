"""Use parent-reviewed, text-only identity anchors in production scene art.

Never interpret metadata flags as permission to upload or process child photos.
"""
from __future__ import annotations

from app.little_legend.blueprint import BookBlueprint
from app.little_legend.character_identity import IdentityBible
from app.little_legend.illustration_runner import production_character_continuity

MAX_CONTINUITY = 1200


def reviewed_identity_continuity(
    *, blueprint: BookBlueprint | None, bible: IdentityBible | None,
    hero_name: str,
) -> str:
    """Merge approved textual anchors with the book-wide fictional hero contract."""
    baseline = production_character_continuity(blueprint)
    if bible is None or not bible.identity.parent_reviewed_description:
        return baseline
    if bible.hero_name != hero_name:
        raise PermissionError("Reviewed identity belongs to another hero")
    if blueprint is not None:
        hero = next((c for c in blueprint.characters if c.role == "hero"), None)
        if hero is not None and hero.name != hero_name:
            raise PermissionError("Hero profile conflicts with reviewed identity")
    identity = bible.identity
    anchors = [
        ("Hair", identity.hair),
        ("Eyes", identity.eyes),
        ("Face", identity.face),
        ("Proportions", identity.proportions),
        ("Clothing signature", identity.clothing_signature),
    ]
    anchors.extend(("Distinctive feature", value) for value in identity.distinctive_features)
    anchors.extend(("Fixed detail", value) for value in identity.fixed_details)
    anchors.extend(("Forbidden change", value) for value in identity.forbidden_changes)
    additions = " ".join(
        f"{label}: {value.strip()}." for label, value in anchors if value.strip()
    )
    if not additions:
        return baseline
    combined = (baseline + " " + additions).strip()
    if len(combined) > MAX_CONTINUITY:
        raise ValueError("Reviewed identity exceeds provider continuity limit")
    return combined
