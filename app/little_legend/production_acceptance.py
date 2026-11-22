"""Operator-safe Little Legend release acceptance gates.

This is a deterministic evaluation of *persisted* production diagnostics.
It does not execute AI, generate assets, contact Telegram or charge a customer.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.delivery_reconciliation import RecoveryAction
from app.little_legend.production_diagnostics import (
    ProductionDiagnostic,
    diagnose_owned_production,
)


class AcceptanceStage(StrEnum):
    PRODUCTION = "production"
    PDF = "pdf"
    DELIVERY = "delivery"


class AcceptanceState(StrEnum):
    PASS = "pass"
    BLOCKED = "blocked"
    REVIEW = "review"


class AcceptanceGate(BaseModel):
    stage: AcceptanceStage
    state: AcceptanceState
    reasons: list[str] = Field(default_factory=list)


class ProductionAcceptance(BaseModel):
    story_id: int = Field(gt=0)
    accepted: bool
    gates: list[AcceptanceGate]


def evaluate_production_acceptance(
    diagnostic: ProductionDiagnostic,
) -> ProductionAcceptance:
    """Only a confirmed sent release passes all three acceptance gates."""
    production_reasons = [
        reason for reason in diagnostic.blockers
        if reason not in {"pdf_not_verified", "delivery_manual_review"}
    ]
    if not diagnostic.manuscript_available and not diagnostic.pdf_registered:
        if "manuscript_unavailable" not in production_reasons:
            production_reasons.append("manuscript_unavailable")
    if diagnostic.manuscript_available and not diagnostic.ready_for_export:
        if not production_reasons:
            production_reasons.append("production_not_ready")
    production_ok = diagnostic.ready_for_export or diagnostic.pdf_registered
    production = AcceptanceGate(
        stage=AcceptanceStage.PRODUCTION,
        state=AcceptanceState.PASS if production_ok and not production_reasons
        else AcceptanceState.BLOCKED,
        reasons=production_reasons,
    )
    pdf = AcceptanceGate(
        stage=AcceptanceStage.PDF,
        state=AcceptanceState.PASS if diagnostic.pdf_registered
        else AcceptanceState.BLOCKED,
        reasons=[] if diagnostic.pdf_registered else ["pdf_not_registered"],
    )
    recovery = diagnostic.delivery_recovery
    if diagnostic.requires_manual_review or recovery in {
        RecoveryAction.MANUAL_REVIEW, RecoveryAction.INCONSISTENT,
        RecoveryAction.IN_FLIGHT, RecoveryAction.REPAIR_PROJECTION,
    }:
        delivery_state = AcceptanceState.REVIEW
        delivery_reasons = ["delivery_requires_reconciliation"]
    elif (
        diagnostic.delivery_status == DeliveryStatus.SENT
        and recovery == RecoveryAction.CONSISTENT
    ):
        delivery_state = AcceptanceState.PASS
        delivery_reasons = []
    else:
        delivery_state = AcceptanceState.BLOCKED
        delivery_reasons = ["delivery_not_confirmed"]
    delivery = AcceptanceGate(
        stage=AcceptanceStage.DELIVERY,
        state=delivery_state,
        reasons=delivery_reasons,
    )
    gates = [production, pdf, delivery]
    return ProductionAcceptance(
        story_id=diagnostic.story_id,
        accepted=all(gate.state == AcceptanceState.PASS for gate in gates),
        gates=gates,
    )


async def assess_owned_production_acceptance(
    *, owner_id: int, story_id: int,
) -> ProductionAcceptance:
    """Read owner-scoped state; never trigger a real customer delivery."""
    diagnostic = await diagnose_owned_production(
        owner_id=owner_id, story_id=story_id,
    )
    return evaluate_production_acceptance(diagnostic)
