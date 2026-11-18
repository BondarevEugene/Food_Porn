"""Explicit image-AI consent and deployment-owned provider disclosure.

Consent for text writing is NOT consent for image generation.
"""
from __future__ import annotations

from dataclasses import dataclass
from os import environ

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ImageAIDisclosure:
    provider: str = ""
    legal_entity: str = ""
    processing_countries: str = ""
    retention_policy: str = ""
    privacy_url: str = ""
    enabled: bool = False

    @property
    def ready(self) -> bool:
        return self.enabled and all((
            self.provider.strip(), self.legal_entity.strip(),
            self.processing_countries.strip(), self.retention_policy.strip(),
            self.privacy_url.startswith("https://"),
        ))

    def notice(self) -> str:
        if not self.ready:
            raise PermissionError("Image AI provider disclosure is incomplete")
        return (
            "Для иллюстраций сказки текстовые описания сцен и персонажей "
            f"передаются {self.provider} ({self.legal_entity}). "
            f"Страны обработки: {self.processing_countries}. "
            f"Хранение и удаление: {self.retention_policy}. "
            f"Политика: {self.privacy_url}. "
            "Фотографии ребёнка не передаются. "
            "Это отдельное согласие на создание изображений."
        )


class ImageAIConsent(BaseModel):
    active: bool = False
    provider: str = Field(default="", max_length=200)
    notice_snapshot: str = Field(default="", max_length=4000)


def configured_image_ai_disclosure() -> ImageAIDisclosure:
    return ImageAIDisclosure(
        provider=environ.get("LL_IMAGE_AI_PROVIDER", ""),
        legal_entity=environ.get("LL_IMAGE_AI_LEGAL_ENTITY", ""),
        processing_countries=environ.get("LL_IMAGE_AI_COUNTRIES", ""),
        retention_policy=environ.get("LL_IMAGE_AI_RETENTION", ""),
        privacy_url=environ.get("LL_IMAGE_AI_PRIVACY_URL", ""),
        enabled=environ.get("LL_IMAGE_AI_CONSENT_ENABLED", "") == "true",
    )


def accept_image_ai_consent(
    *, provider: str, notice: str, terms_accepted: bool,
    disclosure: ImageAIDisclosure,
) -> ImageAIConsent:
    if not terms_accepted:
        raise PermissionError("Parent must accept the terms")
    if provider != disclosure.provider or notice != disclosure.notice():
        raise ValueError("Image AI consent does not match server disclosure")
    return ImageAIConsent(
        active=True, provider=provider, notice_snapshot=notice,
    )


def consent_allows_image_ai(
    consent: ImageAIConsent, disclosure: ImageAIDisclosure,
) -> bool:
    return (
        consent.active and disclosure.ready
        and consent.provider == disclosure.provider
        and consent.notice_snapshot == disclosure.notice()
    )
