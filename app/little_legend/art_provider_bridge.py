"""Approval-gated bridge from story art briefs to a supplied image provider.

No provider, credential, network request, persistence or parental approval is
constructed here. Caller owns all those boundaries and image storage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, Field

from app.little_legend.scene_art_direction import BookArtDirection, SceneArtBrief


class ArtProvider(Protocol):
    async def generate_scene(self, prompt: dict) -> bytes: ...


class SceneArtResult(BaseModel):
    scene_id: str
    image: bytes = Field(min_length=1)
    human_approved: bool = False
    identity_verified: bool = False


@dataclass(frozen=True)
class ArtGenerationPolicy:
    enabled: bool = False
    max_scenes_per_request: int = 4
    max_image_bytes: int = 12 * 1024 * 1024


def scene_art_prompt(brief: SceneArtBrief, *, style: str) -> dict:
    """Stable, auditable provider input; no unapproved character facts added."""
    if not style.strip() or len(style) > 300:
        raise ValueError("A bounded art style is required")
    return {
        "scene_id": brief.scene_id,
        "scene_order": brief.scene_order,
        "hero_name": brief.hero_name,
        "identity_anchor": list(brief.identity_anchor),
        "scene_action": brief.scene_action,
        "setting_and_context": brief.setting_and_context,
        "continuity_rules": list(brief.continuity_rules),
        "forbidden_inventions": list(brief.forbidden_inventions),
        "style": style.strip(),
        "instructions": [
            "Depict the specified scene action, not a generic portrait.",
            "Keep all immutable identity details unchanged across chapters.",
            "Do not invent physical traits, biography or family relationships.",
            "Leave space for book typography; do not draw text into the image.",
        ],
        "parent_review_required": True,
    }


async def generate_scene_candidates(
    provider: ArtProvider,
    direction: BookArtDirection,
    *,
    style: str,
    requested_scene_ids: set[str],
    policy: ArtGenerationPolicy,
) -> list[SceneArtResult]:
    """Produce review-only candidate bytes; never mark images as approved."""
    if not policy.enabled:
        raise PermissionError("Scene art generation is disabled")
    if not direction.human_review_required or direction.images_generated:
        raise ValueError("Only pending, review-gated art direction is supported")
    if policy.max_scenes_per_request < 1 or policy.max_image_bytes < 1:
        raise ValueError("Invalid generation limits")
    by_id = {brief.scene_id: brief for brief in direction.briefs}
    if len(by_id) != len(direction.briefs):
        raise ValueError("Duplicate scene art briefs")
    if not requested_scene_ids or not requested_scene_ids <= set(by_id):
        raise ValueError("Unknown or empty scene selection")
    if len(requested_scene_ids) > policy.max_scenes_per_request:
        raise ValueError("Too many scenes requested")
    # Validate every prompt before making any external calls.
    jobs = [
        scene_art_prompt(by_id[scene_id], style=style)
        for scene_id in sorted(requested_scene_ids, key=lambda key: by_id[key].scene_order)
    ]
    results = []
    for job in jobs:
        raw = await provider.generate_scene(job)
        if not isinstance(raw, bytes) or not raw or len(raw) > policy.max_image_bytes:
            raise ValueError("Provider returned invalid or oversized image bytes")
        results.append(SceneArtResult(scene_id=job["scene_id"], image=raw))
    return results
