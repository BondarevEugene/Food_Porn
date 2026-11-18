"""Parental agreement must be explicit, versioned, revocable and isolated."""
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.little_legend.consent import (
    POLICY_VERSION,
    ConsentDecision,
    ConsentRecord,
    consent_status,
    record_decision,
    withdraw_photo_consent,
)
from app.little_legend.router import STUDIO_HTML, StoryDraft


def test_default_draft_has_no_consent_and_no_upload():
    draft = StoryDraft()
    status = consent_status(draft.consent)
    assert status["terms_accepted"] is False
    assert status["photo_consent_active"] is False
    assert status["photo_upload_enabled"] is False


def test_explicit_parent_and_terms_required():
    for decision in (
        ConsentDecision(),
        ConsentDecision(accept_terms=True),
        ConsentDecision(declare_parental_authority=True),
    ):
        with pytest.raises(ValueError):
            record_decision(ConsentRecord(), decision)


def test_photo_consent_separate_and_revocable():
    accepted = record_decision(
        ConsentRecord(),
        ConsentDecision(accept_terms=True, declare_parental_authority=True),
    )
    assert consent_status(accepted)["terms_accepted"] is True
    assert consent_status(accepted)["photo_consent_active"] is False
    opted_in = record_decision(
        accepted,
        ConsentDecision(
            accept_terms=True, declare_parental_authority=True,
            consent_to_child_photos=True,
        ),
    )
    assert consent_status(opted_in)["photo_consent_active"] is True
    withdrawn = withdraw_photo_consent(opted_in)
    assert consent_status(withdrawn)["photo_consent_active"] is False
    assert consent_status(withdrawn)["photo_upload_enabled"] is False


def test_old_version_requires_new_acceptance():
    old = ConsentRecord(
        version="old",
        terms_accepted_at=datetime.now(UTC),
        parental_authority_declared=True,
        photo_consent_at=datetime.now(UTC),
    )
    assert consent_status(old)["photo_consent_active"] is False


def test_invalid_photo_record_is_rejected():
    with pytest.raises(ValidationError):
        ConsentRecord(photo_consent_at=datetime.now(UTC))


def test_draft_roundtrip_and_studio_revocation_ui():
    draft = StoryDraft(consent=record_decision(
        ConsentRecord(),
        ConsentDecision(accept_terms=True, declare_parental_authority=True),
    ))
    assert StoryDraft.model_validate_json(draft.model_dump_json()).consent.version == POLICY_VERSION
    assert 'id="consentTermsCheck"' in STUDIO_HTML
    assert 'id="consentPhotoCheck"' in STUDIO_HTML
    assert 'withdrawConsent()' in STUDIO_HTML
