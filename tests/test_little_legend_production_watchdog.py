"""No-retry watchdog acceptance tests: deterministic, no Neon or provider calls."""
from datetime import UTC, datetime, timedelta

import pytest

from app.little_legend.production_watchdog import (
    AlertCode,
    WatchdogReport,
    budget_overcommitted,
    classify_fulfillment,
)


NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def check(**overrides):
    kwargs = {
        "status": "pending",
        "created_at": NOW - timedelta(minutes=5),
        "lease_expires_at": None,
        "delivery_started_at": None,
        "delivered_at": None,
        "now": NOW,
    }
    kwargs.update(overrides)
    return classify_fulfillment(**kwargs)


def test_fresh_pending_is_healthy():
    assert check() == set()


def test_old_pending_needs_attention_but_not_retry():
    assert check(created_at=NOW - timedelta(hours=2)) == {
        AlertCode.OLD_PENDING,
    }


def test_live_pdf_lease_not_marked_stale():
    assert check(
        status="processing", lease_expires_at=NOW + timedelta(minutes=1),
    ) == set()


def test_expired_pdf_lease_is_ambiguous():
    assert check(
        status="processing", lease_expires_at=NOW - timedelta(seconds=1),
    ) == {AlertCode.STALE_PDF_LEASE}


def test_processing_without_lease_is_ambiguous():
    assert check(status="processing") == {AlertCode.STALE_PDF_LEASE}


def test_telegram_delivery_claim_without_receipt_requires_operator():
    assert check(
        status="ready", delivery_started_at=NOW - timedelta(minutes=2),
    ) == {AlertCode.DELIVERY_UNCONFIRMED}


def test_telegram_receipt_clears_delivery_warning():
    assert check(
        status="ready", delivery_started_at=NOW - timedelta(minutes=2),
        delivered_at=NOW,
    ) == set()


@pytest.mark.parametrize("status", ["blocked", "failed"])
def test_terminal_failure_needs_manual_review(status):
    assert check(status=status) == {AlertCode.BLOCKED_FULFILLMENT}


def test_overlapping_alerts_preserved():
    assert check(
        status="processing", delivery_started_at=NOW,
    ) == {AlertCode.STALE_PDF_LEASE, AlertCode.DELIVERY_UNCONFIRMED}


@pytest.mark.parametrize(
    ("limit", "held", "spent", "expected"),
    [(100, 0, 0, False), (100, 30, 70, False),
     (100, 60, 60, True), (100, -1, 0, True),
     (0, 0, 0, False)],
)
def test_budget_overcommitment(limit, held, spent, expected):
    assert budget_overcommitted(
        limit_micro_usd=limit, held_micro_usd=held, spent_micro_usd=spent,
    ) is expected


def test_report_never_authorizes_retry():
    report = WatchdogReport(
        checked_at=NOW, total_fulfillment_jobs=10,
        alerts={AlertCode.UNRESOLVED_AI_EFFECTS.value: 2},
        requires_operator=True,
    )
    assert report.automatic_retry_allowed is False
    assert "owner_id" not in report.model_dump_json()
    assert "story_id" not in report.model_dump_json()


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError, match="timezone"):
        check(now=datetime(2026, 11, 20))


def test_invalid_pending_threshold_rejected():
    with pytest.raises(ValueError, match="pending_minutes"):
        check(pending_minutes=0)
