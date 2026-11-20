"""Retention alert lease and deduplication regression tests."""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.little_legend.retention_alert_state import (
    alert_fingerprint,
    claim_alert,
    clear_alert_after_recovery,
    finish_alert,
)


def test_fingerprint_order_independent_and_no_private_text():
    codes = ["RETENTION_DELETE_FAILED", "RETENTION_EXPIRED_BACKLOG"]
    assert alert_fingerprint("critical", codes) == alert_fingerprint(
        "critical", list(reversed(codes)),
    )
    assert len(alert_fingerprint("critical", codes)) == 64


@pytest.mark.parametrize("status", ["ok", "unknown", ""])
def test_invalid_fingerprint_severity(status):
    with pytest.raises(ValueError):
        alert_fingerprint(status, ["RETENTION_DELETE_FAILED"])


def test_unknown_code_rejected():
    with pytest.raises(ValueError):
        alert_fingerprint("warning", ["private/object/key"])


@pytest.mark.asyncio
async def test_invalid_fingerprint_no_database_call():
    session = MagicMock()
    session.execute = AsyncMock()
    with pytest.raises(ValueError):
        await claim_alert(session, fingerprint="not-a-hash")
    session.execute.assert_not_awaited()


def fake_session(row):
    session = MagicMock()
    response = MagicMock()
    response.mappings.return_value.one.return_value = row
    session.execute = AsyncMock(side_effect=[MagicMock(), response, MagicMock()])
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_cooldown_prevents_duplicate_send():
    now = datetime(2026, 11, 20, tzinfo=UTC)
    fingerprint = alert_fingerprint("warning", ["RETENTION_EXPIRED_BACKLOG"])
    session = fake_session({
        "fingerprint": fingerprint,
        "last_sent_at": now - timedelta(minutes=10),
        "lease_token": None,
        "leased_until": None,
    })
    claim = await claim_alert(session, fingerprint=fingerprint, now=now)
    assert claim.token is None
    assert claim.reason == "cooldown"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_lease_blocks_parallel_delivery():
    now = datetime(2026, 11, 20, tzinfo=UTC)
    session = fake_session({
        "fingerprint": "",
        "last_sent_at": None,
        "lease_token": "other-worker",
        "leased_until": now + timedelta(minutes=1),
    })
    claim = await claim_alert(session, fingerprint="a" * 64, now=now)
    assert claim.reason == "delivery_in_progress"
    assert claim.token is None


@pytest.mark.asyncio
async def test_changed_problem_claims_new_delivery():
    now = datetime(2026, 11, 20, tzinfo=UTC)
    session = fake_session({
        "fingerprint": "b" * 64,
        "last_sent_at": now - timedelta(minutes=1),
        "lease_token": None,
        "leased_until": None,
    })
    claim = await claim_alert(session, fingerprint="a" * 64, now=now)
    assert claim.reason == "claimed"
    assert claim.token is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_send_releases_lease():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    await finish_alert(session, token="lease", sent=False)
    session.commit.assert_awaited_once()
    query = session.execute.await_args.args[0]
    assert "last_sent_at" not in query.compile().params


@pytest.mark.asyncio
async def test_recovery_resets_alert_state():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    await clear_alert_after_recovery(session)
    session.commit.assert_awaited_once()
