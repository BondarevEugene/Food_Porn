"""Separate, versioned opt-in for processing children's story text with AI.

Terms acceptance is not consent to share text with an external AI provider.
"""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

TEXT_AI_POLICY_VERSION = "2026-11-18-text-ai-draft-1"


class TextAIConsent(BaseModel):
    version: str = TEXT_AI_POLICY_VERSION
    provider: str = Field(default="", max_length=120)
    accepted_at: datetime | None = None
    withdrawn_at: datetime | None = None
    notice_snapshot: str = Field(default="", max_length=4000)

    @property
    def active(self) -> bool:
        return (
            self.version == TEXT_AI_POLICY_VERSION
            and bool(self.provider.strip())
            and self.accepted_at is not None
            and self.withdrawn_at is None
            and bool(self.notice_snapshot.strip())
        )


class TextAIConsentDecision(BaseModel):
    accepted: bool
    provider: str = Field(min_length=2, max_length=120)
    notice: str = Field(min_length=80, max_length=4000)


def accept_text_ai_consent(
    *, terms_accepted: bool, decision: TextAIConsentDecision,
    provider_configured: str,
    now: datetime | None = None,
) -> TextAIConsent:
    """Bind the opt-in to the disclosed provider and exact notice text."""
    if not terms_accepted:
        raise PermissionError("Terms and parental authority are required")
    if not decision.accepted:
        raise PermissionError("Explicit text AI consent is required")
    if not provider_configured or decision.provider != provider_configured:
        raise ValueError("Disclosed AI provider must match configuration")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Consent timestamp must include timezone")
    return TextAIConsent(
        provider=provider_configured,
        accepted_at=instant,
        notice_snapshot=decision.notice,
    )


def withdraw_text_ai_consent(
    record: TextAIConsent, *, now: datetime | None = None,
) -> TextAIConsent:
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Consent timestamp must include timezone")
    return record.model_copy(update={"withdrawn_at": instant})


def text_ai_consent_status(record: TextAIConsent) -> dict:
    return {
        "active": record.active,
        "provider": record.provider,
        "policy_version": record.version,
        "accepted_at": record.accepted_at,
        "withdrawn_at": record.withdrawn_at,
        "external_generation_enabled": False,
    }
