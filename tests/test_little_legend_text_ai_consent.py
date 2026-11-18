"""Independent text-AI consent must be explicit, scoped and revocable."""
from datetime import UTC, datetime

import pytest

from app.little_legend.text_ai_consent import (
    TextAIConsent,
    TextAIConsentDecision,
    accept_text_ai_consent,
    withdraw_text_ai_consent,
)


def decision():
    return TextAIConsentDecision(
        accepted=True,
        provider="example-ai",
        notice="The story text will be processed by example-ai to write "
        "chapters. The parent can withdraw permission at any time. "
        "No child photos will be processed by this service.",
    )


def test_terms_alone_do_not_enable_external_processing():
    assert not TextAIConsent().active
    with pytest.raises(PermissionError):
        accept_text_ai_consent(
            terms_accepted=False, decision=decision(),
            provider_configured="example-ai",
        )


def test_provider_mismatch_is_rejected():
    with pytest.raises(ValueError, match="provider"):
        accept_text_ai_consent(
            terms_accepted=True, decision=decision(),
            provider_configured="another-ai",
        )


def test_explicit_consent_can_be_withdrawn():
    record = accept_text_ai_consent(
        terms_accepted=True, decision=decision(),
        provider_configured="example-ai",
        now=datetime(2026, 11, 18, tzinfo=UTC),
    )
    assert record.active
    assert record.notice_snapshot == decision().notice
    assert not withdraw_text_ai_consent(record).active
