"""Production diagnostics never mutate customer production."""
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.delivery_reconciliation import RecoveryAction
from app.little_legend.production_diagnostics import diagnose_owned_production


def _session(owned):
    session = AsyncMock()
    result = Mock()
    result.scalar_one_or_none.return_value = owned
    session.execute.return_value = result
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


@pytest.mark.asyncio
async def test_foreign_story_never_exposes_diagnostics():
    with (
        patch("app.little_legend.production_diagnostics.async_session_maker",
              _session(None)),
        patch("app.little_legend.production_diagnostics.get_release_manifest",
              new_callable=AsyncMock) as manifest,
    ):
        with pytest.raises(PermissionError):
            await diagnose_owned_production(owner_id=9, story_id=15)
    manifest.assert_not_awaited()


@pytest.mark.asyncio
async def test_unfinished_story_reports_real_blockers_without_effects():
    readiness = Mock(
        total_scenes=4, completed_scenes=2, ready_for_export=False,
        issues=[Mock(code="illustration_incomplete"),
                Mock(code="illustration_incomplete"),
                Mock(code="editorial_approval_missing")],
    )
    production = Mock()
    production.readiness.return_value = readiness
    with (
        patch("app.little_legend.production_diagnostics.async_session_maker",
              _session(15)),
        patch("app.little_legend.production_diagnostics.get_release_manifest",
              new_callable=AsyncMock, return_value=None),
        patch("app.little_legend.production_diagnostics.load_owned_production",
              new_callable=AsyncMock, return_value=production),
        patch("app.little_legend.production_diagnostics.diagnose_delivery",
              new_callable=AsyncMock) as delivery,
    ):
        result = await diagnose_owned_production(owner_id=9, story_id=15)
    assert result.completed_scenes == 2
    assert result.blockers == ["editorial_approval_missing", "illustration_incomplete"]
    assert result.pdf_registered is False
    delivery.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_delivery_is_flagged_for_operator_not_retried():
    manifest = Mock(status=DeliveryStatus.UNCERTAIN)
    diagnosis = Mock(action=RecoveryAction.MANUAL_REVIEW)
    with (
        patch("app.little_legend.production_diagnostics.async_session_maker",
              _session(15)),
        patch("app.little_legend.production_diagnostics.get_release_manifest",
              new_callable=AsyncMock, return_value=manifest),
        patch("app.little_legend.production_diagnostics.load_owned_production",
              new_callable=AsyncMock, side_effect=PermissionError),
        patch("app.little_legend.production_diagnostics.diagnose_delivery",
              new_callable=AsyncMock, return_value=diagnosis),
    ):
        result = await diagnose_owned_production(owner_id=9, story_id=15)
    assert result.requires_manual_review is True
    assert result.delivery_status == DeliveryStatus.UNCERTAIN
    assert result.delivery_recovery == RecoveryAction.MANUAL_REVIEW
