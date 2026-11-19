"""Owner-only Little Legend recovery API regression tests."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.little_legend.delivery_reconciliation import (
    DeliveryDiagnosis,
    RecoveryAction,
)
from app.little_legend.router import (
    read_delivery_diagnosis,
    reconcile_confirmed_delivery,
)


@pytest.mark.asyncio
async def test_diagnosis_requires_owned_story() -> None:
    with (
        patch(
            "app.little_legend.router._owned_draft",
            new_callable=AsyncMock, side_effect=HTTPException(404, "Not found"),
        ),
        patch(
            "app.little_legend.delivery_reconciliation.diagnose_delivery",
            new_callable=AsyncMock,
        ) as diagnose,
    ):
        with pytest.raises(HTTPException) as exc:
            await read_delivery_diagnosis(story_id=123, owner=42)
    assert exc.value.status_code == 404
    diagnose.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_never_calls_telegram_dispatch() -> None:
    diagnosis = DeliveryDiagnosis(
        owner_id=42, story_id=12, action=RecoveryAction.MANUAL_REVIEW,
        effect_status=None, manifest_status=None,
    )
    with (
        patch("app.little_legend.router._owned_draft", new_callable=AsyncMock),
        patch(
            "app.little_legend.delivery_reconciliation.repair_confirmed_projection",
            new_callable=AsyncMock, return_value=diagnosis,
        ) as repair,
        patch(
            "app.little_legend.release_orchestrator.send_owned_release",
            new_callable=AsyncMock,
        ) as send,
    ):
        result = await reconcile_confirmed_delivery(story_id=12, owner=42)
    assert result["action"] == "manual_review"
    repair.assert_awaited_once_with(owner_id=42, story_id=12)
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_release_returns_not_found() -> None:
    with (
        patch("app.little_legend.router._owned_draft", new_callable=AsyncMock),
        patch(
            "app.little_legend.delivery_reconciliation.diagnose_delivery",
            new_callable=AsyncMock, side_effect=PermissionError("Missing"),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await read_delivery_diagnosis(story_id=12, owner=42)
    assert exc.value.status_code == 404
