"""CRM retention dashboard access and privacy regression checks."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.crm.router import little_legend_retention_operations

STATIC = Path(__file__).resolve().parents[1] / "app" / "crm" / "static"


@pytest.mark.asyncio
async def test_retention_endpoint_requires_owner_before_database():
    with patch(
        "app.crm.router.require_owner",
        side_effect=HTTPException(status_code=403),
    ), patch("app.crm.router.async_session_maker") as factory:
        with pytest.raises(HTTPException) as exc:
            await little_legend_retention_operations(
                identity={"owner": False}, limit=20,
            )
        assert exc.value.status_code == 403
        factory.assert_not_called()


@pytest.mark.asyncio
async def test_retention_endpoint_returns_only_aggregates():
    rows = [{
        "id": 1, "status": "ok", "codes": [],
        "expired_not_deleted": 0,
    }]
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    with patch("app.crm.router.require_owner"), patch(
        "app.crm.router.async_session_maker", return_value=context,
    ), patch(
        "app.crm.router.recent_retention_runs",
        new_callable=AsyncMock, return_value=rows,
    ) as history:
        result = await little_legend_retention_operations(
            identity={"owner": True}, limit=5,
        )
    history.assert_awaited_once_with(session, limit=5)
    assert result["latest"] == rows[0]
    assert result["total_returned"] == 1
    assert result["read_only"] is True
    assert result["photo_upload_enabled_by_this_endpoint"] is False


def test_retention_dashboard_fetches_owner_only_endpoint():
    source = (STATIC / "crm.js").read_text(encoding="utf-8")
    assert "/little-legend/retention-operations?limit=20" in source
    assert "Приватное хранилище · Retention" in source
    assert "retentionRows" in source
    assert "expired_not_deleted" in source
