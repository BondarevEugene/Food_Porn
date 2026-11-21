"""Photo-consent persistence is owner-scoped and revocation queues erasure."""
from app.little_legend.neon_premium_photo_consent import premium_photo_consents
from app.little_legend.premium_photo_consent import PremiumPhotoConsent


def test_neon_consent_schema_has_no_photograph_bytes():
    columns = premium_photo_consents.c
    assert "owner_id" in columns
    assert "story_id" in columns
    assert "notice_snapshot" in columns
    assert "accepted_at" in columns
    assert "withdrawn_at" in columns
    assert not any(
        name in columns for name in ("image", "photo_bytes", "raw_photo")
    )


def test_missing_consent_is_disabled():
    consent = PremiumPhotoConsent()
    assert not consent.active
    assert consent.accepted_at is None
