"""Telegram delivery receipt contract and manual recovery safeguards."""
from datetime import UTC, datetime

from app.little_legend.fulfillment_queue import fulfillment_jobs
from app.little_legend.production_leases import LeaseDiagnosis
from app.little_legend.production_operations import (
    ProductionOperationsView,
    RecoveryAction,
    recommend_recovery,
)


def test_receipt_column_is_in_fulfillment_mapping():
    assert "telegram_message_id" in fulfillment_jobs.c
    assert fulfillment_jobs.c.telegram_message_id.nullable


def test_operations_exposes_confirmed_delivery_receipt():
    now = datetime.now(UTC)
    view = ProductionOperationsView(
        quote_id=11,
        story_id=21,
        fulfillment_status="ready",
        lease_diagnosis=LeaseDiagnosis.READY,
        lease_attempts=1,
        recovery_action=RecoveryAction.READY,
        unresolved_effects=0,
        held_reservations=0,
        delivery_started_at=now,
        delivered_at=now,
        telegram_message_id=98765,
    )
    assert view.model_dump(mode="json")["telegram_message_id"] == 98765


def test_unconfirmed_delivery_is_never_assumed_confirmed():
    view = ProductionOperationsView(
        quote_id=11,
        story_id=21,
        fulfillment_status="ready",
        lease_diagnosis=LeaseDiagnosis.READY,
        lease_attempts=1,
        recovery_action=RecoveryAction.MANUAL_REVIEW,
        unresolved_effects=0,
        held_reservations=0,
        delivery_started_at=datetime.now(UTC),
    )
    assert view.delivered_at is None
    assert view.telegram_message_id is None
    assert not view.automatic_retry_allowed


def test_recovery_does_not_authorize_retry_after_ambiguous_effects():
    action, _ = recommend_recovery(
        diagnosis=LeaseDiagnosis.READY,
        unresolved_effects=1,
        held_reservations=0,
        has_budget=True,
    )
    assert action is RecoveryAction.MANUAL_REVIEW
