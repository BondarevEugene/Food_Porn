"""Payment claim idempotency for both primary digital products."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.models import MenuStatus
from app.database.repositories import MenuRepository, WallpaperOrderRepository


def fake_session(record):
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = record
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["menu", "wallpaper"])
async def test_repeated_payment_is_noop(kind):
    record = SimpleNamespace(id=7, payment_id="receipt-1", payment_system="portmone",
                             is_paid=True, paid=True)
    session = fake_session(record)
    if kind == "menu":
        changed = await MenuRepository(session).mark_as_paid(7, "receipt-1", "portmone")
    else:
        changed = await WallpaperOrderRepository(session).mark_paid(
            record, "receipt-1", "portmone"
        )
    assert changed is False
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["menu", "wallpaper"])
async def test_conflicting_receipt_is_rejected(kind):
    record = SimpleNamespace(id=7, payment_id="receipt-1", payment_system="portmone",
                             is_paid=True, paid=True)
    session = fake_session(record)
    with pytest.raises(ValueError, match="another receipt"):
        if kind == "menu":
            await MenuRepository(session).mark_as_paid(7, "receipt-2", "portmone")
        else:
            await WallpaperOrderRepository(session).mark_paid(
                record, "receipt-2", "portmone"
            )
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_payment_requires_waiting_invoice():
    record = SimpleNamespace(id=7, is_paid=False, status=MenuStatus.DRAFT)
    session = fake_session(record)
    with pytest.raises(ValueError, match="no payable invoice"):
        await MenuRepository(session).mark_as_paid(7, "receipt-1", "portmone")
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
