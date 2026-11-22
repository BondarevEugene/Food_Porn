"""Read-only production acceptance regression scenarios."""
from unittest.mock import AsyncMock, patch

import pytest

from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.delivery_reconciliation import RecoveryAction
from app.little_legend.production_acceptance import (
    AcceptanceState,
    assess_owned_production_acceptance,
    evaluate_production_acceptance,
)
from app.little_legend.production_diagnostics import ProductionDiagnostic


def snapshot(**changes):
    data = dict(
        story_id=12, manuscript_available=True, total_scenes=4,
        completed_scenes=4, ready_for_export=True, pdf_registered=True,
        delivery_status=DeliveryStatus.SENT,
        delivery_recovery=RecoveryAction.CONSISTENT,
        blockers=["pdf_not_verified"], requires_manual_review=False,
    )
    data.update(changes)
    return ProductionDiagnostic(**data)


def test_confirmed_sealed_book_passes_all_gates():
    result = evaluate_production_acceptance(snapshot())
    assert result.accepted is True
    assert [gate.state for gate in result.gates] == [
        AcceptanceState.PASS, AcceptanceState.PASS, AcceptanceState.PASS,
    ]


@pytest.mark.parametrize(
    ("change", "delivery_state"),
    [
        ({"delivery_status": DeliveryStatus.READY,
          "delivery_recovery": RecoveryAction.NO_EFFECT}, AcceptanceState.BLOCKED),
        ({"delivery_status": DeliveryStatus.UNCERTAIN,
          "delivery_recovery": RecoveryAction.MANUAL_REVIEW}, AcceptanceState.REVIEW),
        ({"delivery_status": DeliveryStatus.READY,
          "delivery_recovery": RecoveryAction.REPAIR_PROJECTION}, AcceptanceState.REVIEW),
        ({"delivery_status": DeliveryStatus.READY,
          "delivery_recovery": RecoveryAction.IN_FLIGHT}, AcceptanceState.REVIEW),
        ({"delivery_status": DeliveryStatus.SENT,
          "delivery_recovery": RecoveryAction.INCONSISTENT}, AcceptanceState.REVIEW),
    ],
)
def test_unconfirmed_delivery_never_passes(change, delivery_state):
    result = evaluate_production_acceptance(snapshot(**change))
    assert result.accepted is False
    assert result.gates[2].state == delivery_state


def test_incomplete_illustration_blocks_acceptance():
    result = evaluate_production_acceptance(snapshot(
        ready_for_export=False, completed_scenes=2,
        blockers=["illustration_incomplete", "pdf_not_verified"],
    ))
    assert not result.accepted
    assert result.gates[0].state == AcceptanceState.BLOCKED


def test_missing_pdf_blocks_acceptance():
    result = evaluate_production_acceptance(snapshot(pdf_registered=False))
    assert not result.accepted
    assert result.gates[1].state == AcceptanceState.BLOCKED


@pytest.mark.asyncio
async def test_owner_scoped_acceptance_is_read_only():
    with patch(
        "app.little_legend.production_acceptance.diagnose_owned_production",
        new_callable=AsyncMock, return_value=snapshot(),
    ) as diagnose:
        result = await assess_owned_production_acceptance(
            owner_id=42, story_id=12,
        )
    assert result.accepted
    diagnose.assert_awaited_once_with(owner_id=42, story_id=12)


@pytest.mark.asyncio
async def test_foreign_story_is_rejected():
    with patch(
        "app.little_legend.production_acceptance.diagnose_owned_production",
        new_callable=AsyncMock, side_effect=PermissionError("Story not found"),
    ):
        with pytest.raises(PermissionError):
            await assess_owned_production_acceptance(owner_id=42, story_id=12)
