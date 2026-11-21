"""Bridge live Neon photo assets to premium book visual planning.

Never use the raw photograph or an unscoped asset identifier in a job payload.
"""
from __future__ import annotations

from app.little_legend.neon_photo_vault import NeonVaultMetadataRepository
from app.little_legend.neon_premium_photo_consent import (
    NeonPremiumPhotoConsentRepository,
)
from app.little_legend.premium_photo_consent import (
    configured_premium_photo_disclosure,
    premium_photo_consent_allows_transfer,
)
from app.little_legend.premium_visual_contract import (
    BookGenre,
    BookVisualPlan,
    build_visual_plan,
)


async def build_owned_photo_visual_plan(
    *, owner_id: int, story_id: int, genre: BookGenre,
    chapter_moments: list[tuple[str, str]],
    photos: NeonVaultMetadataRepository | None = None,
    consents: NeonPremiumPhotoConsentRepository | None = None,
) -> BookVisualPlan:
    """Construct a scene-specific plan from authorized, live private photo IDs."""
    if owner_id <= 0 or story_id <= 0:
        raise PermissionError("Book not found")
    consent_repo = consents or NeonPremiumPhotoConsentRepository()
    consent = await consent_repo.get_photo_consent(
        owner_id=owner_id, story_id=story_id,
    )
    if not premium_photo_consent_allows_transfer(
        consent, configured_premium_photo_disclosure(),
    ):
        raise PermissionError("Current parental photo AI consent is required")
    photo_repo = photos or NeonVaultMetadataRepository()
    reference_ids = await photo_repo.list_stored_reference_ids(
        owner_id=owner_id, story_id=story_id,
    )
    if not reference_ids:
        raise PermissionError("No active private reference photos")
    return build_visual_plan(
        genre=genre, reference_ids=reference_ids,
        chapter_moments=chapter_moments,
    )
