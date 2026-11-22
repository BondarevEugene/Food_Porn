"""Read-only, owner-scoped Little Legend production diagnostics.

No AI generation, payment, Telegram dispatch, PDF writes or child text output.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.delivery_reconciliation import (
    RecoveryAction,
    diagnose_delivery,
)
from app.little_legend.owned_production import load_owned_production
from app.little_legend.release_manifest_store import get_release_manifest


class ProductionDiagnostic(BaseModel):
    story_id: int = Field(gt=0)
    manuscript_available: bool
    total_scenes: int = Field(ge=0)
    completed_scenes: int = Field(ge=0)
    ready_for_export: bool
    pdf_registered: bool
    delivery_status: DeliveryStatus | None = None
    delivery_recovery: RecoveryAction | None = None
    blockers: list[str] = Field(default_factory=list)
    requires_manual_review: bool = False


async def diagnose_owned_production(
    *, owner_id: int, story_id: int,
) -> ProductionDiagnostic:
    """Collect persisted state only; never change production or send files."""
    if owner_id <= 0 or story_id <= 0:
        raise PermissionError("Invalid story owner")
    manifest = await get_release_manifest(owner_id=owner_id, story_id=story_id)
    blockers: list[str] = []
    total = completed = 0
    ready = False
    manuscript_available = False
    try:
        production = await load_owned_production(
            owner_id=owner_id, story_id=story_id,
        )
    except PermissionError:
        # A sealed release can outlive the current draft. For unsealed stories
        # a missing manuscript is an explicit production blocker.
        if manifest is None:
            blockers.append("manuscript_unavailable")
    else:
        manuscript_available = True
        readiness = production.readiness()
        total = readiness.total_scenes
        completed = readiness.completed_scenes
        ready = readiness.ready_for_export
        blockers.extend(sorted({issue.code for issue in readiness.issues}))
    recovery = None
    if manifest is not None:
        diagnosis = await diagnose_delivery(
            owner_id=owner_id, story_id=story_id,
        )
        recovery = diagnosis.action
        if recovery in {RecoveryAction.MANUAL_REVIEW, RecoveryAction.INCONSISTENT}:
            blockers.append("delivery_manual_review")
    return ProductionDiagnostic(
        story_id=story_id,
        manuscript_available=manuscript_available,
        total_scenes=total,
        completed_scenes=completed,
        ready_for_export=ready,
        pdf_registered=manifest is not None,
        delivery_status=manifest.status if manifest else None,
        delivery_recovery=recovery,
        blockers=blockers,
        requires_manual_review="delivery_manual_review" in blockers,
    )
