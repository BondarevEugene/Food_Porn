"""Production queue must reject orders without a verified receipt."""
from unittest.mock import AsyncMock

import pytest

from app.little_legend import fulfillment_queue


@pytest.mark.asyncio
async def test_unpaid_quote_cannot_enqueue(monkeypatch):
    check = AsyncMock(return_value=False)
    monkeypatch.setattr(fulfillment_queue, "has_verified_entitlement", check)
    session = AsyncMock()

    with pytest.raises(PermissionError, match="Verified payment required"):
        await fulfillment_queue.request_paid_fulfillment(
            session, quote_id=19, owner_id=42
        )

    session.execute.assert_not_awaited()
    check.assert_awaited_once_with(session, quote_id=19, owner_id=42)
