"""Consent-gated photo-to-visual-plan handoff regression coverage."""
from datetime import UTC, datetime

import pytest

from app.little_legend.owned_photo_visual_plan import build_owned_photo_visual_plan
from app.little_legend.premium_photo_consent import (
    PremiumPhotoConsent,
    PremiumPhotoDisclosure,
)
from app.little_legend.premium_visual_contract import BookGenre


class ConsentRepo:
    def __init__(self, consent):
        self.consent = consent

    async def get_photo_consent(self, *, owner_id, story_id):
        assert (owner_id, story_id) == (5, 7)
        return self.consent


class PhotoRepo:
    def __init__(self, ids):
        self.ids = ids
        self.calls = 0

    async def list_stored_reference_ids(self, *, owner_id, story_id):
        self.calls += 1
        assert (owner_id, story_id) == (5, 7)
        return self.ids


@pytest.mark.asyncio
async def test_photo_plan_requires_consent_before_access(monkeypatch):
    photos = PhotoRepo(["a" * 48])
    with pytest.raises(PermissionError, match="consent"):
        await build_owned_photo_visual_plan(
            owner_id=5, story_id=7, genre=BookGenre.FAIRY_TALE,
            chapter_moments=[("forest", "river")],
            photos=photos, consents=ConsentRepo(PremiumPhotoConsent()),
        )
    assert photos.calls == 0


@pytest.mark.asyncio
async def test_photo_plan_assigns_private_references_to_distinct_scenes(monkeypatch):
    disclosure = PremiumPhotoDisclosure(
        provider="Provider", legal_entity="Legal entity",
        processing_countries="EU", retention_policy="7 days",
        privacy_url="https://example.com/privacy", enabled=True,
    )
    monkeypatch.setattr(
        "app.little_legend.owned_photo_visual_plan.configured_premium_photo_disclosure",
        lambda: disclosure,
    )
    photos = PhotoRepo(["a" * 48, "b" * 48])
    plan = await build_owned_photo_visual_plan(
        owner_id=5, story_id=7, genre=BookGenre.FAIRY_TALE,
        chapter_moments=[("forest", "river"), ("mountain", "castle")],
        photos=photos,
        consents=ConsentRepo(PremiumPhotoConsent(
            active=True, provider="Provider", notice_snapshot=disclosure.notice(),
            accepted_at=datetime.now(UTC),
        )),
    )
    assert plan.cover_reference_id == "a" * 48
    assert len(plan.illustrations) == 4
    assert [x.source_reference_id for x in plan.illustrations] == [
        "a" * 48, "b" * 48, "a" * 48, "b" * 48,
    ]
    assert len({x.moment_id for x in plan.illustrations}) == 4
