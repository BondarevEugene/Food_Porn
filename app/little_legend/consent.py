"""Versioned parental declarations for Little Legend.

Consent is a prerequisite for future photo handling, NOT permission to start
uploading: image storage and third-party processing remain disabled.
"""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, model_validator

POLICY_VERSION = "2026-11-18-draft-1"
TERMS = (
    "Вы подтверждаете, что достигли совершеннолетия, имеете право предоставлять "
    "материалы и являетесь родителем или законным представителем ребёнка. "
    "Вы обязуетесь не загружать незаконные материалы, материалы с нарушением "
    "чужих прав и изображения детей без необходимого разрешения. "
    "Материалы используются исключительно для выполнения вашего заказа. "
    "Мы не продаём, не публикуем и не используем их для рекламы или обучения "
    "собственных моделей без отдельного разрешения. Для создания книги может "
    "потребоваться передача минимально необходимых данных техническим "
    "подрядчикам; конкретные получатели и условия должны быть раскрыты "
    "до включения обработки фотографий."
)
PHOTO_NOTICE = (
    "Отдельное согласие на обработку фотографий ребёнка для создания "
    "персонализированной книги. Согласие добровольное, может быть отозвано. "
    "До запуска функции должны быть опубликованы сведения об операторе, "
    "AI-провайдерах, странах обработки, сроках хранения и порядке удаления. "
    "В этой версии загрузка и обработка фотографий отключены."
)


class ConsentRecord(BaseModel):
    version: str = POLICY_VERSION
    terms_accepted_at: datetime | None = None
    parental_authority_declared: bool = False
    photo_consent_at: datetime | None = None
    photo_consent_withdrawn_at: datetime | None = None

    @model_validator(mode="after")
    def check_consistency(self) -> ConsentRecord:
        if self.photo_consent_at and (
            not self.terms_accepted_at or not self.parental_authority_declared
        ):
            raise ValueError("Photo consent requires terms and parental authority")
        return self

    @property
    def photo_consent_active(self) -> bool:
        return (
            self.version == POLICY_VERSION
            and self.photo_consent_at is not None
            and self.photo_consent_withdrawn_at is None
        )


class ConsentDecision(BaseModel):
    accept_terms: bool = False
    declare_parental_authority: bool = False
    consent_to_child_photos: bool = False


def record_decision(
    previous: ConsentRecord, decision: ConsentDecision
) -> ConsentRecord:
    if not decision.accept_terms or not decision.declare_parental_authority:
        raise ValueError("Terms and parental authority must be confirmed")
    if decision.consent_to_child_photos:
        raise ValueError("Photo consent is unavailable until the final privacy notice is published")
    now = datetime.now(UTC)
    return ConsentRecord(
        version=POLICY_VERSION,
        terms_accepted_at=now,
        parental_authority_declared=True,
        photo_consent_at=now if decision.consent_to_child_photos else None,
    )


def withdraw_photo_consent(previous: ConsentRecord) -> ConsentRecord:
    return previous.model_copy(update={
        "photo_consent_withdrawn_at": datetime.now(UTC),
    })


def consent_status(record: ConsentRecord) -> dict:
    return {
        "version": POLICY_VERSION,
        "terms_accepted": (
            record.version == POLICY_VERSION
            and record.terms_accepted_at is not None
            and record.parental_authority_declared
        ),
        "photo_consent_active": record.photo_consent_active,
        "photo_upload_enabled": False,
        "photo_processing_enabled": False,
        "privacy_policy_finalized": False,
    }
