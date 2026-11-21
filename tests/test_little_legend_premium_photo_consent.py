"""Explicit photo transfer consent must not be confused with text-only AI consent."""
from app.little_legend.premium_photo_consent import (
    PremiumPhotoDisclosure,
    accept_premium_photo_consent,
    premium_photo_consent_allows_transfer,
    withdraw_premium_photo_consent,
)


def _disclosure():
    return PremiumPhotoDisclosure(
        provider="OpenAI", legal_entity="OpenAI",
        processing_countries="United States",
        retention_policy="Seven days",
        privacy_url="https://example.com/privacy",
        enabled=True,
    )


def test_notice_explicitly_discloses_photo_transfer():
    disclosure = _disclosure()
    assert "фотография" in disclosure.notice()
    assert "передаётся" in disclosure.notice()


def test_photo_transfer_requires_separate_parental_consent():
    disclosure = _disclosure()
    consent = accept_premium_photo_consent(
        provider="OpenAI", notice=disclosure.notice(),
        parent_authorized=True, disclosure=disclosure,
    )
    assert premium_photo_consent_allows_transfer(consent, disclosure)
    assert not premium_photo_consent_allows_transfer(
        withdraw_premium_photo_consent(consent), disclosure,
    )


def test_change_of_provider_or_notice_invalidates_prior_consent():
    disclosure = _disclosure()
    consent = accept_premium_photo_consent(
        provider="OpenAI", notice=disclosure.notice(),
        parent_authorized=True, disclosure=disclosure,
    )
    changed = PremiumPhotoDisclosure(
        provider="Other", legal_entity="Other",
        processing_countries="EU", retention_policy="One day",
        privacy_url="https://example.com/privacy", enabled=True,
    )
    assert not premium_photo_consent_allows_transfer(consent, changed)
