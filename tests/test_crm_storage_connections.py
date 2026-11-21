"""Neon-backed storage registry contracts."""
from unittest.mock import AsyncMock, Mock

import pytest

from app.crm.storage_connections import KEY, load, resolve, save, validate


def connection():
    return {
        "bot_id": "food_porn", "name": "assets", "prefix": "food-porn/",
        "endpoint_env": "ENDPOINT_URL", "bucket_env": "BUCKET_NAME",
        "region_env": "REGION_NAME", "access_env": "ACCESS_KEY",
        "secret_env": "SECRET_KEY",
    }


def test_registry_accepts_environment_references_only():
    assert validate([connection()]) == [connection()]
    with pytest.raises(ValueError):
        validate([{**connection(), "secret_env": "actual-secret"}])


def test_registry_resolves_environment():
    values = {
        "ENDPOINT_URL": "https://r2.example.test", "BUCKET_NAME": "private",
        "REGION_NAME": "auto", "ACCESS_KEY": "key", "SECRET_KEY": "secret",
    }
    targets = resolve([connection()], values)
    assert targets[0]["configured"] is True
    assert targets[0]["bot_id"] == "food_porn"


@pytest.mark.asyncio
async def test_registry_persists_to_existing_settings():
    session = AsyncMock()
    session.get.return_value = None
    await save(session, [connection()])
    session.add.assert_called_once()
    row = session.add.call_args.args[0]
    assert row.key == KEY
    assert "food-porn/" in row.value


@pytest.mark.asyncio
async def test_missing_registry_is_empty():
    session = Mock()
    session.get = AsyncMock(return_value=None)
    assert await load(session) == []
