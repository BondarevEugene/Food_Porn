"""Child-data lifecycle and fail-closed launch readiness.

No image bytes, biometric templates, URLs or external API calls are accepted.
These are explicit metadata controls, not a claim of end-to-end data erasure.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.little_legend.character_identity import IdentityBible
from app.little_legend.portrait_studio import PortraitPlan


class PrivacyLaunchConfig(BaseModel):
    """Administrative checklist only: never enables photo processing."""

    operator_fop_name: str = Field(default="", max_length=180)
    privacy_contact: str = Field(default="", max_length=200)
    published_policy_version: str = Field(default="", max_length=80)
    processor_register_reviewed: bool = False
    deletion_procedure_reviewed: bool = False
    legal_review_completed: bool = False
    access_control_reviewed: bool = False
    upload_security_reviewed: bool = False
    retention_schedule_reviewed: bool = False
    external_processor_contracts_reviewed: bool = False


class LifecycleEvent(BaseModel):
    kind: Literal["photo_consent_withdrawn", "portrait_reset"]
    details: str = Field(max_length=240)


def photo_launch_preflight(config: PrivacyLaunchConfig) -> dict:
    checks = {
        "registered_fop": bool(config.operator_fop_name.strip()),
        "privacy_contact": bool(config.privacy_contact.strip()),
        "policy_version": bool(config.published_policy_version.strip()),
        "processor_register": config.processor_register_reviewed,
        "deletion_procedure": config.deletion_procedure_reviewed,
        "legal_review": config.legal_review_completed,
        "access_control": config.access_control_reviewed,
        "upload_security": config.upload_security_reviewed,
        "retention_schedule": config.retention_schedule_reviewed,
        "processor_contracts": config.external_processor_contracts_reviewed,
    }
    return {
        "checks": checks,
        "missing": [name for name, ok in checks.items() if not ok],
        "checklist_complete": all(checks.values()),
        "photo_upload_enabled": False,
        "photo_processing_enabled": False,
        "automatic_deletion_enabled": False,
        "reason": "Requires separate implementation and independent security review",
    }


def reset_photo_approvals(
    bible: IdentityBible | None, plan: PortraitPlan
) -> tuple[IdentityBible | None, PortraitPlan, list[LifecycleEvent]]:
    """Clear photo-related approvals without deleting user-authored descriptions."""
    new_bible = bible.model_copy(deep=True) if bible is not None else None
    if new_bible is not None:
        new_bible.identity.parental_photo_consent = False
        new_bible.identity.portrait_review = "not_started"
    new_plan = plan.model_copy(deep=True)
    new_plan.reference_photo_reviewed = False
    return new_bible, new_plan, [
        LifecycleEvent(
            kind="photo_consent_withdrawn",
            details="Photo permissions and portrait approval flags reset",
        ),
    ]
