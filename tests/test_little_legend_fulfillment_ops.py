"""Operational diagnosis must not mutate payments or retry delivery."""
from datetime import UTC, datetime, timedelta

from app.little_legend.fulfillment_ops import diagnose


def row(status, *, started=None, delivered=None, minutes=0):
    return {
        "status": status,
        "delivery_started_at": started,
        "delivered_at": delivered,
        "updated_at": datetime.now(UTC) - timedelta(minutes=minutes),
    }


def test_ambiguous_telegram_delivery_is_not_safe_to_retry():
    now = datetime.now(UTC)
    assert diagnose(row("ready", started=now), now=now) == (
        "telegram_delivery_requires_reconciliation"
    )


def test_delivered_is_final():
    now = datetime.now(UTC)
    assert diagnose(row("ready", started=now, delivered=now), now=now) == "delivered"


def test_stale_processing_is_visible():
    now = datetime.now(UTC)
    assert diagnose(row("processing", minutes=40), now=now) == (
        "possibly_stalled_render"
    )


def test_unstarted_ready_book_can_be_sent():
    now = datetime.now(UTC)
    assert diagnose(row("ready"), now=now) == "ready_for_telegram"


def test_blocked_requires_review():
    now = datetime.now(UTC)
    assert diagnose(row("blocked"), now=now) == (
        "review_story_illustrations_or_storage"
    )
