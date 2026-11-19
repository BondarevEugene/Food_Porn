"""CRM recovery endpoints enforce owner role before any database access."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.crm.router import (
    little_legend_delivery_detail,
    little_legend_delivery_queue,
    little_legend_delivery_repair,
)


@pytest.mark.asyncio
async def test_vip_cannot_read_global_recovery_queue() -> None:
    with patch(
        "app.crm.router.async_session_maker",
    ) as session:
        with pytest.raises(HTTPException) as exc:
            await little_legend_delivery_queue(
                identity={"owner": False, "actor": "vip"},
                limit=50,
            )
    assert exc.value.status_code == 403
    session.assert_not_called()


@pytest.mark.asyncio
async def test_vip_cannot_diagnose_another_customers_book() -> None:
    with patch(
        "app.little_legend.delivery_reconciliation.diagnose_delivery",
        new_callable=AsyncMock,
    ) as diagnose:
        with pytest.raises(HTTPException) as exc:
            await little_legend_delivery_detail(
                owner_id=42, story_id=12,
                identity={"owner": False, "actor": "vip"},
            )
    assert exc.value.status_code == 403
    diagnose.assert_not_awaited()


@pytest.mark.asyncio
async def test_vip_cannot_repair_delivery() -> None:
    with patch(
        "app.little_legend.delivery_reconciliation.repair_confirmed_projection",
        new_callable=AsyncMock,
    ) as repair:
        with pytest.raises(HTTPException) as exc:
            await little_legend_delivery_repair(
                owner_id=42, story_id=12,
                identity={"owner": False, "actor": "vip"},
            )
    assert exc.value.status_code == 403
    repair.assert_not_awaited()
