"""Production Operations must fail closed and never authorize repeat AI."""
import pytest

from app.little_legend.production_leases import LeaseDiagnosis
from app.little_legend.production_operations import (
    ProductionOperationsView,
    RecoveryAction,
    recommend_recovery,
)
from app.little_legend.release_control_center import RELEASE_CONTROL_HTML


@pytest.mark.parametrize("diagnosis", [LeaseDiagnosis.STALE_REVIEW, LeaseDiagnosis.FAILED_REVIEW])
def test_crashed_or_failed_worker_needs_manual_review(diagnosis):
    action, notes = recommend_recovery(
        diagnosis=diagnosis, unresolved_effects=0,
        held_reservations=0, has_budget=True,
    )
    assert action == RecoveryAction.MANUAL_REVIEW
    assert notes


@pytest.mark.parametrize("effects,held", [(1, 0), (0, 1), (3, 4)])
def test_unreconciled_effect_or_held_budget_blocks_retry(effects, held):
    action, _ = recommend_recovery(
        diagnosis=LeaseDiagnosis.QUEUED,
        unresolved_effects=effects, held_reservations=held, has_budget=True,
    )
    assert action == RecoveryAction.MANUAL_REVIEW


def test_active_worker_waits():
    action, _ = recommend_recovery(
        diagnosis=LeaseDiagnosis.ACTIVE, unresolved_effects=0,
        held_reservations=0, has_budget=True,
    )
    assert action == RecoveryAction.WAIT


def test_pending_without_budget_blocked():
    action, _ = recommend_recovery(
        diagnosis=LeaseDiagnosis.QUEUED, unresolved_effects=0,
        held_reservations=0, has_budget=False,
    )
    assert action == RecoveryAction.BLOCKED


def test_pending_with_budget_is_queued_not_authorized_to_dispatch():
    action, _ = recommend_recovery(
        diagnosis=LeaseDiagnosis.QUEUED, unresolved_effects=0,
        held_reservations=0, has_budget=True,
    )
    assert action == RecoveryAction.QUEUED


def test_ready_does_not_claim_telegram_delivery():
    action, notes = recommend_recovery(
        diagnosis=LeaseDiagnosis.READY, unresolved_effects=0,
        held_reservations=0, has_budget=True,
    )
    assert action == RecoveryAction.READY
    assert "delivery" in notes[0]


def test_negative_counters_rejected():
    with pytest.raises(ValueError):
        recommend_recovery(
            diagnosis=LeaseDiagnosis.QUEUED, unresolved_effects=-1,
            held_reservations=0, has_budget=True,
        )


def test_retry_is_always_disabled_even_if_model_constructed():
    view = ProductionOperationsView(
        quote_id=1, story_id=2, fulfillment_status="pending",
        lease_diagnosis=LeaseDiagnosis.QUEUED, lease_attempts=0,
        recovery_action=RecoveryAction.QUEUED,
    )
    assert view.automatic_retry_allowed is False


def test_dashboard_shows_read_only_budget_and_effect_diagnostics():
    assert "/order-quotes/'+id+'/production-operations" in RELEASE_CONTROL_HTML
    assert 'id="productionBudget"' in RELEASE_CONTROL_HTML
    assert 'id="productionHeld"' in RELEASE_CONTROL_HTML
    assert 'id="productionSpent"' in RELEASE_CONTROL_HTML
    assert 'id="productionEffects"' in RELEASE_CONTROL_HTML
    assert "method:'POST'" in RELEASE_CONTROL_HTML  # existing delivery reconcile only
    assert RELEASE_CONTROL_HTML.count("method:'POST'") == 1
