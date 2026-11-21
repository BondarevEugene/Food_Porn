"""Retention eligibility never claims deletion without physical R2 erasure."""
from datetime import UTC, datetime, timedelta

from app.little_legend.neon_photo_retention import MAX_ATTEMPTS, _due
from app.little_legend.secure_vault import AssetState


def _row(state, *, attempts=0, expires=None):
    return {
        "state": state.value,
        "deletion_attempts": attempts,
        "expires_at": expires or datetime.now(UTC) - timedelta(days=1),
    }


def test_expired_stored_and_reserved_are_eligible():
    now = datetime.now(UTC)
    assert _due(_row(AssetState.STORED), now)
    assert _due(_row(AssetState.RESERVED), now)


def test_unexpired_and_deleted_are_never_erased():
    now = datetime.now(UTC)
    future = now + timedelta(days=1)
    assert not _due(_row(AssetState.STORED, expires=future), now)
    assert not _due(_row(AssetState.DELETED), now)


def test_failed_erasure_is_bounded_and_due_only_after_expiry():
    now = datetime.now(UTC)
    assert _due(_row(AssetState.DELETE_FAILED, attempts=MAX_ATTEMPTS - 1), now)
    assert not _due(_row(AssetState.DELETE_FAILED, attempts=MAX_ATTEMPTS), now)
    assert not _due(
        _row(
            AssetState.DELETE_FAILED, attempts=1,
            expires=now + timedelta(days=1),
        ), now,
    )
