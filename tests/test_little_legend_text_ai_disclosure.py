"""Server-side disclosure must be complete and immutable to callers."""
import pytest

from app.little_legend.text_ai_consent import TextAIConsentDecision
from app.little_legend.text_ai_disclosure import (
    TextAIProviderDisclosure,
    accept_server_disclosure,
    consent_allows_provider,
)


def disclosure():
    return TextAIProviderDisclosure(
        provider="example-ai", legal_entity="Example AI Ltd",
        processing_countries="EU", retention_policy="Delete after 30 days",
        privacy_url="https://example.org/privacy", enabled=True,
    )


def test_incomplete_disclosure_is_disabled():
    assert not TextAIProviderDisclosure(enabled=True).ready
    with pytest.raises(PermissionError):
        TextAIProviderDisclosure(enabled=True).notice()


def test_client_cannot_replace_notice_or_provider():
    configured = disclosure()
    with pytest.raises(ValueError, match="current server disclosure"):
        accept_server_disclosure(
            terms_accepted=True, disclosure=configured,
            decision=TextAIConsentDecision(
                accepted=True, provider="example-ai",
                notice="A different notice " * 10,
            ),
        )


def test_consent_is_bound_to_exact_disclosure_and_revocation():
    configured = disclosure()
    consent = accept_server_disclosure(
        terms_accepted=True, disclosure=configured,
        decision=TextAIConsentDecision(
            accepted=True, provider=configured.provider,
            notice=configured.notice(),
        ),
    )
    assert consent_allows_provider(consent, configured)
    assert not consent_allows_provider(
        consent, TextAIProviderDisclosure(
            **{**configured.__dict__, "retention_policy": "Delete after 7 days"}
        ),
    )
