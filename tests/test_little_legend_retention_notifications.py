"""Privacy and opt-in alert transport regression tests."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.little_legend.retention_notifications import (
    alert_message,
    notify_retention,
)


def test_healthy_has_no_notification():
    assert alert_message({"status": "ok", "codes": []}) is None


def test_message_only_contains_allowlisted_codes():
    message = alert_message({
        "status": "critical",
        "codes": ["RETENTION_DELETE_FAILED", "RETENTION_RETRY_EXHAUSTED"],
        "owner_id": "secret",
        "object_key": "private/secret",
    })
    assert message is not None
    assert "RETENTION_DELETE_FAILED" in message
    assert "secret" not in message


def test_unknown_code_fails_closed():
    with pytest.raises(ValueError, match="Unknown"):
        alert_message({"status": "warning", "codes": ["secret"]})


def test_invalid_severity_fails_closed():
    with pytest.raises(ValueError, match="status"):
        alert_message({"status": "panic", "codes": []})


@pytest.mark.asyncio
async def test_no_credentials_does_not_send():
    result = await notify_retention(
        {"status": "warning", "codes": ["RETENTION_EXPIRED_BACKLOG"]},
        token="", chat_id="",
    )
    assert result is False


@pytest.mark.asyncio
async def test_healthy_does_not_send_even_with_credentials():
    result = await notify_retention(
        {"status": "ok", "codes": []},
        token="123:abc", chat_id="123",
    )
    assert result is False


@pytest.mark.asyncio
async def test_invalid_token_fails_before_network():
    with pytest.raises(ValueError, match="token"):
        await notify_retention(
            {"status": "warning", "codes": ["RETENTION_EXPIRED_BACKLOG"]},
            token="bad/token", chat_id="123",
        )


@pytest.mark.asyncio
async def test_transport_sends_aggregate_only():
    response = MagicMock()
    response.json.return_value = {"ok": True}
    response.raise_for_status.return_value = None
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    with patch(
        "app.little_legend.retention_notifications.httpx.AsyncClient",
        return_value=context,
    ):
        sent = await notify_retention(
            {"status": "warning", "codes": ["RETENTION_EXPIRED_BACKLOG"]},
            token="123:abc", chat_id="123",
        )
    assert sent is True
    kwargs = client.post.await_args.kwargs
    assert kwargs["json"]["chat_id"] == "123"
    assert "RETENTION_EXPIRED_BACKLOG" in kwargs["json"]["text"]
