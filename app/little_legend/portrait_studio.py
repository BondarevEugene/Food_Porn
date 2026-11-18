"""Non-biometric, metadata-only portrait readiness workflow.

Never stores or accepts photographs, URLs, image embeddings or reference bytes.
All photo-processing capabilities are deliberately disabled pending legal review.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.little_legend.character_identity import IdentityBible
from app.little_legend.consent import ConsentRecord, consent_status


class PortraitPlan(BaseModel):
    mode: Literal["quick", "director"] = "quick"
    style: str = Field(default="storybook", max_length=120)
    preferred_outfit: str = Field(default="", max_length=250)
    expression: str = Field(default="natural smile", max_length=120)
    background: str = Field(default="neutral", max_length=150)
    framing: Literal["head-and-shoulders", "half-body", "full-body"] = "head-and-shoulders"
    lighting: str = Field(default="soft natural light", max_length=120)
    avoid: list[str] = Field(default_factory=list, max_length=12)
    parent_description_approved: bool = False
    reference_photo_reviewed: bool = False

    @model_validator(mode="after")
    def forbid_photo_approval(self) -> PortraitPlan:
        if self.reference_photo_reviewed:
            raise ValueError("Reference photo review is unavailable without secure photo processing")
        return self


def portrait_preflight(
    plan: PortraitPlan, identity: IdentityBible, consent: ConsentRecord
) -> dict:
    """Explain missing prerequisites without suggesting an image was analyzed."""
    blockers: list[str] = []
    status = consent_status(consent)
    if not status["terms_accepted"]:
        blockers.append("Примите пользовательское соглашение и подтвердите полномочия родителя")
    if not status["photo_consent_active"]:
        blockers.append("Отдельное согласие на фотографии пока недоступно")
    if not identity.identity.parent_reviewed_description:
        blockers.append("Подтвердите текстовое описание внешности ребёнка")
    if not plan.parent_description_approved:
        blockers.append("Утвердите настройки эталонного портрета")
    if not any((
        identity.identity.hair.strip(),
        identity.identity.eyes.strip(),
        identity.identity.face.strip(),
    )):
        blockers.append("Добавьте опорные черты внешности")
    blockers.append("Защищённая загрузка и обработка фотографий ещё не запущены")
    return {
        "blockers": blockers,
        "description_ready": (
            identity.identity.parent_reviewed_description
            and plan.parent_description_approved
        ),
        "photo_upload_enabled": False,
        "portrait_generation_enabled": False,
        "face_similarity_measured": False,
        "human_approval_required": True,
        "provider_configured": False,
    }
