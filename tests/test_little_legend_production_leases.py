"""Fail-closed production leases and migration contract."""

from datetime import UTC, datetime, timedelta

import pytest

from app.little_legend.fulfillment_queue import fulfillment_jobs
from app.little_legend.production_leases import (
    LeaseDiagnosis,
    ProductionState,
    _duration,
    diagnose_lease,
)


def test_pending_never_claims_processing_without_explicit_transition():
    assert diagnose_lease(status="pending", expires_at=None) == LeaseDiagnosis.QUEUED


def test_live_processing_is_active():
    now = datetime.now(UTC)
    assert diagnose_lease(
        status="processing", expires_at=now + timedelta(seconds=40), now=now,
    ) == LeaseDiagnosis.ACTIVE


def test_expired_processing_requires_manual_reconciliation():
    now = datetime.now(UTC)
    assert diagnose_lease(
        status="processing", expires_at=now - timedelta(seconds=1), now=now,
    ) == LeaseDiagnosis.STALE_REVIEW
    assert diagnose_lease(
        status="processing", expires_at=None, now=now,
    ) == LeaseDiagnosis.STALE_REVIEW


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("ready", LeaseDiagnosis.READY),
        ("failed", LeaseDiagnosis.FAILED_REVIEW),
        ("blocked", LeaseDiagnosis.BLOCKED),
    ],
)
def test_terminal_states_are_never_requeued(status, expected):
    assert diagnose_lease(status=status, expires_at=None) == expected


def test_unknown_state_fails_closed():
    with pytest.raises(ValueError, match="Unknown"):
        diagnose_lease(status="retrying", expires_at=None)


@pytest.mark.parametrize("seconds", [0, 29, 3601, True, -1])
def test_lease_duration_is_bounded(seconds):
    with pytest.raises(ValueError):
        _duration(seconds)


def test_lease_duration_accepts_supported_range():
    assert _duration(30) == timedelta(seconds=30)
    assert _duration(3600) == timedelta(hours=1)


def test_schema_contains_fencing_token_and_attempt_counter():
    assert "lease_token" in fulfillment_jobs.c
    assert "lease_expires_at" in fulfillment_jobs.c
    assert "lease_attempts" in fulfillment_jobs.c
    assert ProductionState.PROCESSING.value == "processing"
