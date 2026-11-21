"""Immutable, budget-bounded manifest for a premium book illustration batch.

This is a deterministic planning and validation layer. Paid provider dispatch
remains forbidden until the queue's revision, consent and ledger fences support
premium moment IDs and the independently personalized cover.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_UP

from pydantic import BaseModel, Field, model_validator

from app.little_legend.premium_visual_contract import BookVisualPlan


class PremiumArtRequest(BaseModel):
    moment_id: str = Field(min_length=1, max_length=100)
    chapter_index: int = Field(ge=0)
    reference_id: str = Field(min_length=1)
    scene_description: str = Field(min_length=1)
    costume_direction: str = Field(min_length=1)
    background_direction: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    estimated_micro_usd: int = Field(gt=0)
    requires_identity_review: bool = True
    requires_face_safe_margin: bool = True


class PremiumBatchManifest(BaseModel):
    owner_id: int = Field(gt=0)
    story_id: int = Field(gt=0)
    genre: str
    requests: tuple[PremiumArtRequest, ...]
    total_estimated_micro_usd: int = Field(gt=0)
    max_budget_micro_usd: int = Field(gt=0)
    fingerprint: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_manifest(self) -> PremiumBatchManifest:
        if not self.requests or self.requests[0].moment_id != "premium-cover":
            raise ValueError("The personalized cover must be first")
        if len(self.requests) > 41:
            raise ValueError("Premium batch exceeds 40 illustrations and one cover")
        if len({item.moment_id for item in self.requests}) != len(self.requests):
            raise ValueError("Premium illustration moment IDs must be unique")
        if self.total_estimated_micro_usd != sum(
            item.estimated_micro_usd for item in self.requests
        ):
            raise ValueError("Premium batch cost does not match request sum")
        if self.total_estimated_micro_usd > self.max_budget_micro_usd:
            raise ValueError("Premium illustration batch exceeds its budget")
        return self


def _micro_usd(amount: str) -> int:
    try:
        value = Decimal(amount)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Invalid image unit cost") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("Image unit cost must be positive and finite")
    return int((value * 1_000_000).to_integral_value(rounding=ROUND_UP))


def build_premium_batch_manifest(
    *,
    owner_id: int,
    story_id: int,
    plan: BookVisualPlan,
    chapter_revisions: list[int],
    image_unit_cost_usd: str = "0.05",
    max_budget_usd: str = "5.00",
) -> PremiumBatchManifest:
    """Reserve estimated cost for every distinct moment, including the cover.

    No raw photo bytes or provider prompts are stored in this manifest.
    """
    if owner_id <= 0 or story_id <= 0:
        raise ValueError("Valid owner and story are required")
    chapter_count = len(plan.illustrations) // 2
    if len(chapter_revisions) != chapter_count or any(
        not isinstance(rev, int) or isinstance(rev, bool) or rev < 0
        for rev in chapter_revisions
    ):
        raise ValueError("A valid revision is required for every chapter")
    unit = _micro_usd(image_unit_cost_usd)
    budget = _micro_usd(max_budget_usd)
    requests = [PremiumArtRequest(
        moment_id="premium-cover",
        chapter_index=0,
        reference_id=plan.cover_reference_id,
        scene_description="Personalized cover portrait of the story hero",
        costume_direction="Genre-appropriate cover costume",
        background_direction="Story-world cover composition",
        expected_revision=max(chapter_revisions),
        estimated_micro_usd=unit,
    )]
    for slot in plan.illustrations:
        requests.append(PremiumArtRequest(
            moment_id=slot.moment_id,
            chapter_index=slot.chapter_index,
            reference_id=slot.source_reference_id,
            scene_description=slot.scene_description,
            costume_direction=slot.costume_direction,
            background_direction=slot.background_direction,
            expected_revision=chapter_revisions[slot.chapter_index - 1],
            estimated_micro_usd=unit,
        ))
    # Content-addressed identity: changing chapter revisions, scenes, style
    # or reference assignment produces a different manifest fingerprint.
    payload = {
        "owner_id": owner_id,
        "story_id": story_id,
        "genre": plan.genre.value,
        "design": plan.design.model_dump(mode="json"),
        "requests": [request.model_dump(mode="json") for request in requests],
    }
    fingerprint = hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return PremiumBatchManifest(
        owner_id=owner_id, story_id=story_id, genre=plan.genre.value,
        requests=tuple(requests),
        total_estimated_micro_usd=unit * len(requests),
        max_budget_micro_usd=budget,
        fingerprint=fingerprint,
    )
