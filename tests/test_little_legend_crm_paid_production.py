"""The CRM production endpoint is owner-only and delegates to read-only diagnostics."""
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.crm import router as crm_router
from app.little_legend import fulfillment_ops


@pytest.mark.asyncio
async def test_paid_production_owner_only(monkeypatch):
    report = AsyncMock(return_value={"counts": {}, "orders": []})
    monkeypatch.setattr(fulfillment_ops, "report", report)
    monkeypatch.setattr(crm_router, "require_owner", lambda identity: None)

    result = await crm_router.little_legend_paid_production(
        identity={"actor": "owner"}, limit=25
    )
    assert result["orders"] == []
    report.assert_awaited_once_with(limit=25)


@pytest.mark.asyncio
async def test_paid_production_denies_non_owner(monkeypatch):
    report = AsyncMock()
    monkeypatch.setattr(fulfillment_ops, "report", report)

    def deny(identity):
        raise HTTPException(status_code=403, detail="Owner required")

    monkeypatch.setattr(crm_router, "require_owner", deny)
    with pytest.raises(HTTPException) as error:
        await crm_router.little_legend_paid_production(
            identity={"actor": "viewer"}, limit=25
        )
    assert error.value.status_code == 403
    report.assert_not_awaited()
