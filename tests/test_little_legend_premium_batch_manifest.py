"""Premium batch manifest: deterministic budgeting and strict scene coverage."""
import pytest
from pydantic import ValidationError

from app.little_legend.premium_batch_manifest import (
    PremiumBatchManifest,
    build_premium_batch_manifest,
)
from app.little_legend.premium_visual_contract import BookGenre, build_visual_plan


def _plan(chapters=12):
    return build_visual_plan(
        genre=BookGenre.EPIC_FANTASY,
        reference_ids=["photo-a", "photo-b", "photo-c"],
        chapter_moments=[
            (f"Chapter {index} discovery", f"Chapter {index} consequence")
            for index in range(1, chapters + 1)
        ],
    )


def test_twelve_chapters_have_25_unique_requests_and_cover():
    manifest = build_premium_batch_manifest(
        owner_id=7, story_id=19, plan=_plan(),
        chapter_revisions=[2] * 12,
    )
    assert len(manifest.requests) == 25
    assert len({request.moment_id for request in manifest.requests}) == 25
    assert manifest.requests[0].moment_id == "premium-cover"
    assert [request.reference_id for request in manifest.requests[1:7]] == [
        "photo-a", "photo-b", "photo-c", "photo-a", "photo-b", "photo-c",
    ]
    assert manifest.total_estimated_micro_usd == 1_250_000
    assert all(request.requires_identity_review for request in manifest.requests)
    assert all(request.requires_face_safe_margin for request in manifest.requests)


def test_fingerprint_is_stable_and_changes_with_revision():
    args = dict(owner_id=7, story_id=19, plan=_plan(2))
    first = build_premium_batch_manifest(**args, chapter_revisions=[1, 1])
    second = build_premium_batch_manifest(**args, chapter_revisions=[1, 1])
    changed = build_premium_batch_manifest(**args, chapter_revisions=[1, 2])
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != changed.fingerprint


def test_budget_includes_cover_and_rounds_cost_up():
    manifest = build_premium_batch_manifest(
        owner_id=7, story_id=19, plan=_plan(1),
        chapter_revisions=[0], image_unit_cost_usd="0.0000001",
    )
    assert manifest.total_estimated_micro_usd == 3
    with pytest.raises(ValueError):
        build_premium_batch_manifest(
            owner_id=7, story_id=19, plan=_plan(12),
            chapter_revisions=[0] * 12,
            image_unit_cost_usd="0.25",
        )


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity", "not-a-price"])
def test_invalid_price_rejected(amount):
    with pytest.raises(ValueError):
        build_premium_batch_manifest(
            owner_id=7, story_id=19, plan=_plan(1),
            chapter_revisions=[0], image_unit_cost_usd=amount,
        )


def test_invalid_revisions_and_manifest_tampering_rejected():
    with pytest.raises(ValueError):
        build_premium_batch_manifest(
            owner_id=7, story_id=19, plan=_plan(2),
            chapter_revisions=[1],
        )
    manifest = build_premium_batch_manifest(
        owner_id=7, story_id=19, plan=_plan(1), chapter_revisions=[1],
    )
    with pytest.raises(ValidationError):
        PremiumBatchManifest.model_validate({
            **manifest.model_dump(),
            "total_estimated_micro_usd": 1,
        })
