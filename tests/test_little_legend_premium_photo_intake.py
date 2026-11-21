"""Security regression tests for consent-gated private photo intake."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.little_legend.premium_photo_consent import (
    PremiumPhotoConsent,
    PremiumPhotoDisclosure,
)
from app.little_legend.premium_photo_intake import upload_consented_child_photo


@pytest.mark.asyncio
async def test_photo_upload_denied_without_persisted_parent_consent():
    vault = AsyncMock()
    consents = AsyncMock()
    consents.get_photo_consent.return_value = PremiumPhotoConsent()
    disclosure = PremiumPhotoDisclosure(
        provider="Example", legal_entity="Example Ltd",
        processing_countries="EU", retention_policy="7 days",
        privacy_url="https://example.com/privacy", enabled=True,
    )
    with patch(
        "app.little_legend.premium_photo_intake.configured_premium_photo_disclosure",
        return_value=disclosure,
    ):
        with pytest.raises(PermissionError):
            await upload_consented_child_photo(
                owner_id=10, story_id=20, data=b"private",
                vault=vault, consents=consents,
            )
    vault.upload_private_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_photo_upload_uses_database_consent_not_boolean_from_client():
    vault = AsyncMock()
    consents = AsyncMock()
    disclosure = PremiumPhotoDisclosure(
        provider="Example", legal_entity="Example Ltd",
        processing_countries="EU", retention_policy="7 days",
        privacy_url="https://example.com/privacy", enabled=True,
    )
    consents.get_photo_consent.return_value = PremiumPhotoConsent(
        active=True, provider=disclosure.provider,
        notice_snapshot=disclosure.notice(), accepted_at=datetime.now(UTC),
    )
    with patch(
        "app.little_legend.premium_photo_intake.configured_premium_photo_disclosure",
        return_value=disclosure,
    ):
        await upload_consented_child_photo(
            owner_id=10, story_id=20, data=b"private",
            vault=vault, consents=consents,
        )
    vault.upload_private_photo.assert_awaited_once_with(
        owner_id=10, story_id=20, data=b"private", consent_confirmed=True,
    )


@pytest.mark.asyncio
async def test_photo_upload_rejects_disabled_provider_before_storage():
    vault = AsyncMock()
    consents = AsyncMock()
    with patch(
        "app.little_legend.premium_photo_intake.configured_premium_photo_disclosure",
        return_value=PremiumPhotoDisclosure(),
    ):
        with pytest.raises(PermissionError):
            await upload_consented_child_photo(
                owner_id=10, story_id=20, data=b"private",
                vault=vault, consents=consents,
            )
    vault.upload_private_photo.assert_not_awaited()
    consents.get_photo_consent.assert_not_awaited()
