"""Consent audit writes and withdrawal queue integration."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.little_legend.consent_registry import (
    ConsentEventType,
    append_consent_event,
    withdraw_and_queue_private_media,
)


@pytest.mark.asyncio
async def test_consent_events_are_owner_scoped():
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    with pytest.raises(PermissionError):
        await append_consent_event(
            session, owner_id=10, story_id=20,
            event_type=ConsentEventType.TERMS_ACCEPTED,
        )


@pytest.mark.asyncio
async def test_invalid_identity_rejected_before_database_access():
    session = MagicMock()
    with pytest.raises(ValueError):
        await append_consent_event(
            session, owner_id=0, story_id=1,
            event_type=ConsentEventType.PHOTO_WITHDRAWN,
        )
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_withdrawal_queues_deletion_after_audit_event():
    session = MagicMock()
    with (
        patch(
            "app.little_legend.consent_registry.append_consent_event",
            new_callable=AsyncMock,
        ) as event,
        patch(
            "app.little_legend.consent_registry.queue_story_deletion",
            new_callable=AsyncMock, return_value=3,
        ) as queue,
    ):
        assert await withdraw_and_queue_private_media(
            session, owner_id=5, story_id=9
        ) == 3
        event.assert_awaited_once()
        assert event.await_args.kwargs["event_type"] == (
            ConsentEventType.PHOTO_WITHDRAWN
        )
        queue.assert_awaited_once_with(
            session, owner_id=5, story_id=9
        )


@pytest.mark.asyncio
async def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError):
        await append_consent_event(
            MagicMock(), owner_id=1, story_id=2,
            event_type=ConsentEventType.TERMS_ACCEPTED,
            now=datetime(2026, 1, 1),
        )


def test_audit_event_does_not_grant_photo_consent():
    assert set(ConsentEventType) == {
        ConsentEventType.TERMS_ACCEPTED,
        ConsentEventType.PHOTO_WITHDRAWN,
    }
