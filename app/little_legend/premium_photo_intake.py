"""Verified premium child-photo intake: no caller-supplied consent bypass.

The service is transport-agnostic: Telegram and HTTP must both use this gate.
Photo bytes are never persisted to Neon or logged.
"""
from __future__ import annotations

from app.little_legend.neon_premium_photo_consent import (
    NeonPremiumPhotoConsentRepository,
)
from app.little_legend.premium_photo_consent import (
    configured_premium_photo_disclosure,
    premium_photo_consent_allows_transfer,
)
from app.little_legend.private_photo_vault import AuthorizedPrivatePhotoVault
from app.little_legend.secure_vault import VaultAsset


async def upload_consented_child_photo(
    *, owner_id: int, story_id: int, data: bytes,
    vault: AuthorizedPrivatePhotoVault,
    consents: NeonPremiumPhotoConsentRepository,
) -> VaultAsset:
    """Fail closed before touching private storage or creating metadata."""
    if owner_id <= 0 or story_id <= 0:
        raise PermissionError("Story not found")
    disclosure = configured_premium_photo_disclosure()
    if not disclosure.ready:
        raise PermissionError("Premium photo handling is disabled")
    consent = await consents.get_photo_consent(
        owner_id=owner_id, story_id=story_id,
    )
    if not premium_photo_consent_allows_transfer(consent, disclosure):
        raise PermissionError("Active parental photo consent required")
    return await vault.upload_private_photo(
        owner_id=owner_id, story_id=story_id,
        data=data, consent_confirmed=True,
    )


async def erase_consented_child_photos(
    *, owner_id: int, story_id: int,
    consents: NeonPremiumPhotoConsentRepository,
) -> None:
    """Revoke consent and queue physical deletion in the same DB transaction."""
    await consents.withdraw(owner_id=owner_id, story_id=story_id)
