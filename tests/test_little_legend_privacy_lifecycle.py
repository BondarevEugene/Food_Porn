"""Privacy readiness is fail-closed and withdrawal clears portrait approvals."""
from datetime import UTC, datetime

from app.little_legend.character_identity import IdentityBible, VisualIdentity
from app.little_legend.consent import ConsentRecord, consent_status, withdraw_photo_consent
from app.little_legend.portrait_studio import PortraitPlan
from app.little_legend.privacy_lifecycle import (
    PrivacyLaunchConfig,
    photo_launch_preflight,
    reset_photo_approvals,
)
from app.little_legend.router import STUDIO_HTML, StoryDraft


def test_preflight_never_enables_upload_even_with_every_check_complete():
    config = PrivacyLaunchConfig(
        operator_fop_name="ФОП Тестовий",
        privacy_contact="privacy@example.test",
        published_policy_version="v1",
        processor_register_reviewed=True,
        deletion_procedure_reviewed=True,
        legal_review_completed=True,
        access_control_reviewed=True,
        upload_security_reviewed=True,
        retention_schedule_reviewed=True,
        external_processor_contracts_reviewed=True,
    )
    status = photo_launch_preflight(config)
    assert status["checklist_complete"] is True
    assert status["photo_upload_enabled"] is False
    assert status["photo_processing_enabled"] is False
    assert status["automatic_deletion_enabled"] is False


def test_withdrawal_resets_identity_photo_flags_not_description():
    bible = IdentityBible(
        hero_name="Оля",
        identity=VisualIdentity(
            hair="тёмные", eyes="карие",
            parental_photo_consent=True, portrait_review="approved",
            parent_reviewed_description=True,
        ),
    )
    original = PortraitPlan(parent_description_approved=True)
    updated_bible, updated_plan, events = reset_photo_approvals(bible, original)
    assert updated_bible is not None
    assert updated_bible.identity.parental_photo_consent is False
    assert updated_bible.identity.portrait_review == "not_started"
    assert updated_bible.identity.hair == "тёмные"
    assert updated_bible.identity.parent_reviewed_description is True
    assert updated_plan.parent_description_approved is True
    assert bible.identity.portrait_review == "approved"
    assert events[0].kind == "photo_consent_withdrawn"


def test_revoked_consent_stays_inactive():
    record = ConsentRecord(
        terms_accepted_at=datetime.now(UTC),
        parental_authority_declared=True,
        photo_consent_at=datetime.now(UTC),
    )
    assert consent_status(record)["photo_consent_active"] is True
    assert consent_status(withdraw_photo_consent(record))["photo_consent_active"] is False


def test_legacy_story_and_privacy_ui():
    draft = StoryDraft.model_validate({"title": "Сказка"})
    assert draft.identity_bible is None
    assert photo_launch_preflight(PrivacyLaunchConfig())["missing"]
    assert 'id="privacyChecks"' in STUDIO_HTML
    assert "privacy-readiness" in STUDIO_HTML
