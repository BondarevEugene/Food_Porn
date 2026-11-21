"""Separate, fail-closed parental consent for AI processing of child photos.

Text-to-image consent explicitly says no photos are transferred and therefore
cannot authorize the premium image-edit provider. This contract prevents
accidental reuse of the old consent for a materially different data flow.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from os import environ

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class PremiumPhotoDisclosure:
    provider: str = ""
    legal_entity: str = ""
    processing_countries: str = ""
    retention_policy: str = ""
    privacy_url: str = ""
    enabled: bool = False

    @property
    def ready(self) -> bool:
        return self.enabled and all((
            self.provider.strip(),
            self.legal_entity.strip(),
            self.processing_countries.strip(),
            self.retention_policy.strip(),
            self.privacy_url.startswith("https://"),
        ))

    def notice(self) -> str:
        if not self.ready:
            raise PermissionError("Premium photo disclosure is incomplete")
        return (
            "Для создания персонализированных иллюстраций фотография "
            "ребёнка передаётся стороннему AI-провайдеру "
            f"{self.provider} ({self.legal_entity}). "
            f"Страны обработки: {self.processing_countries}. "
            f"Сроки хранения и удаления: {self.retention_policy}. "
            f"Политика конфиденциальности: {self.privacy_url}. "
            "Согласие на передачу фотографии является отдельным "
            "от согласия на генерацию иллюстраций без фотографии."
        )


class PremiumPhotoConsent(BaseModel):
    active: bool = False
    provider: str = Field(default="", max_length=200)
    notice_snapshot: str = Field(default="", max_length=4000)
    accepted_at: datetime | None = None
    withdrawn_at: datetime | None = None


def configured_premium_photo_disclosure() -> PremiumPhotoDisclosure:
    return PremiumPhotoDisclosure(
        provider=environ.get("LL_PREMIUM_PHOTO_AI_PROVIDER", ""),
        legal_entity=environ.get("LL_PREMIUM_PHOTO_AI_LEGAL_ENTITY", ""),
        processing_countries=environ.get("LL_PREMIUM_PHOTO_AI_COUNTRIES", ""),
        retention_policy=environ.get("LL_PREMIUM_PHOTO_AI_RETENTION", ""),
        privacy_url=environ.get("LL_PREMIUM_PHOTO_AI_PRIVACY_URL", ""),
        enabled=environ.get("LL_PREMIUM_PHOTO_AI_CONSENT_ENABLED") == "true",
    )


def accept_premium_photo_consent(
    *, provider: str, notice: str, parent_authorized: bool,
    disclosure: PremiumPhotoDisclosure,
) -> PremiumPhotoConsent:
    if not parent_authorized:
        raise PermissionError("Parent or legal guardian authorization required")
    if provider != disclosure.provider or notice != disclosure.notice():
        raise PermissionError("Premium photo notice is outdated or mismatched")
    return PremiumPhotoConsent(
        active=True, provider=provider, notice_snapshot=notice,
        accepted_at=datetime.now(UTC),
    )


def withdraw_premium_photo_consent(
    consent: PremiumPhotoConsent,
) -> PremiumPhotoConsent:
    return consent.model_copy(update={
        "active": False,
        "withdrawn_at": datetime.now(UTC),
    })


def premium_photo_consent_allows_transfer(
    consent: PremiumPhotoConsent, disclosure: PremiumPhotoDisclosure,
) -> bool:
    return bool(
        consent.active
        and consent.accepted_at is not None
        and consent.withdrawn_at is None
        and disclosure.ready
        and consent.provider == disclosure.provider
        and consent.notice_snapshot == disclosure.notice()
    )
