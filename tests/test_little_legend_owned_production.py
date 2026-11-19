"""Owner-scoped production loading and readiness endpoint contracts."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.little_legend.owned_production import load_owned_production
from app.little_legend.router import read_production_readiness


@pytest.mark.asyncio
async def test_invalid_owner_never_opens_database() -> None:
    with patch(
        "app.little_legend.owned_production.async_session_maker",
    ) as session:
        with pytest.raises(PermissionError, match="not found"):
            await load_owned_production(owner_id=0, story_id=1)
    session.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_story_never_opens_database() -> None:
    with patch(
        "app.little_legend.owned_production.async_session_maker",
    ) as session:
        with pytest.raises(PermissionError, match="not found"):
            await load_owned_production(owner_id=1, story_id=-1)
    session.assert_not_called()


@pytest.mark.asyncio
async def test_readiness_endpoint_masks_foreign_or_missing_story() -> None:
    with patch(
        "app.little_legend.owned_production.load_owned_production",
        new_callable=AsyncMock,
        side_effect=PermissionError("Story not found"),
    ):
        with pytest.raises(HTTPException) as error:
            await read_production_readiness(story_id=3, owner=12)
    assert error.value.status_code == 404
    assert "owner" not in str(error.value.detail).lower()


@pytest.mark.asyncio
async def test_readiness_endpoint_returns_machine_readable_report() -> None:
    from unittest.mock import Mock

    production = Mock()
    report = Mock()
    report.model_dump.return_value = {
        "ready_for_export": False,
        "ready_for_delivery": False,
        "completed_scenes": 0,
        "total_scenes": 1,
        "issues": [{"code": "chapter_missing", "stage": "manuscript"}],
    }
    production.readiness.return_value = report
    with patch(
        "app.little_legend.owned_production.load_owned_production",
        new_callable=AsyncMock,
        return_value=production,
    ) as load:
        result = await read_production_readiness(story_id=3, owner=12)
    load.assert_awaited_once_with(owner_id=12, story_id=3)
    assert result["issues"][0]["code"] == "chapter_missing"
