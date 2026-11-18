"""Server-owned disclosure and explicit opt-in for Little Legend text AI.

All configuration is disabled by default. No child photos are permitted.
"""
from __future__ import annotations

from dataclasses import dataclass
from os import environ

from app.little_legend.text_ai_consent import (
    TextAIConsent,
    TextAIConsentDecision,
    accept_text_ai_consent,
)


@dataclass(frozen=True)
class TextAIProviderDisclosure:
    provider: str = ""
    legal_entity: str = ""
    processing_countries: str = ""
    retention_policy: str = ""
    privacy_url: str = ""
    enabled: bool = False

    @property
    def ready(self) -> bool:
        return (
            self.enabled
            and all((
                self.provider.strip(), self.legal_entity.strip(),
                self.processing_countries.strip(), self.retention_policy.strip(),
                self.privacy_url.startswith("https://"),
            ))
        )

    def notice(self) -> str:
        if not self.ready:
            raise PermissionError("Text AI provider disclosure is incomplete")
        return (
            "Для написания персональной сказки текст истории и сведения о "
            "персонажах будут переданы AI-провайдеру "
            f"{self.provider} ({self.legal_entity}). "
            f"Страны обработки: {self.processing_countries}. "
            f"Хранение и удаление: {self.retention_policy}. "
            f"Политика конфиденциальности: {self.privacy_url}. "
            "Фотографии ребёнка не передаются. Согласие можно отозвать."
        )


def configured_text_ai_disclosure() -> TextAIProviderDisclosure:
    """Read only deployment-owned environment values, never client input."""
    return TextAIProviderDisclosure(
        provider=environ.get("LL_TEXT_AI_PROVIDER", ""),
        legal_entity=environ.get("LL_TEXT_AI_LEGAL_ENTITY", ""),
        processing_countries=environ.get("LL_TEXT_AI_COUNTRIES", ""),
        retention_policy=environ.get("LL_TEXT_AI_RETENTION", ""),
        privacy_url=environ.get("LL_TEXT_AI_PRIVACY_URL", ""),
        enabled=environ.get("LL_TEXT_AI_CONSENT_ENABLED", "") == "true",
    )


def accept_server_disclosure(
    *, decision: TextAIConsentDecision, terms_accepted: bool,
    disclosure: TextAIProviderDisclosure,
) -> TextAIConsent:
    """Reject consent to a stale, edited or attacker-supplied disclosure."""
    notice = disclosure.notice()
    if decision.provider != disclosure.provider or decision.notice != notice:
        raise ValueError("Consent must match the current server disclosure")
    return accept_text_ai_consent(
        terms_accepted=terms_accepted, decision=decision,
        provider_configured=disclosure.provider,
    )


def consent_allows_provider(
    record: TextAIConsent, disclosure: TextAIProviderDisclosure,
) -> bool:
    """Trusted worker must check immediately before every provider call."""
    return (
        record.active and disclosure.ready
        and record.provider == disclosure.provider
        and record.notice_snapshot == disclosure.notice()
    )
