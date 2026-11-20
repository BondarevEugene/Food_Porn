"""Safety and continuity contracts for the opt-in AI production worker."""
from unittest.mock import AsyncMock

import pytest

from app.little_legend import ai_production_runner as runner


def test_ai_production_is_disabled_by_default():
    with pytest.raises(PermissionError, match="LL_AI_PRODUCTION_ENABLED"):
        runner.validate_ai_production(mode="writer", env={})


def test_writer_requires_explicit_provider_and_disclosure():
    with pytest.raises(PermissionError, match="LL_WRITER_ENABLED"):
        runner.validate_ai_production(
            mode="writer", env={"LL_AI_PRODUCTION_ENABLED": "true"},
        )


def test_illustration_requires_private_art_storage():
    with pytest.raises(PermissionError, match="LITTLE_LEGEND_ART_S3_ENDPOINT"):
        runner.validate_ai_production(
            mode="illustration",
            env={
                "LL_AI_PRODUCTION_ENABLED": "true",
                "LL_ILLUSTRATION_ENABLED": "true",
                "LL_IMAGE_AI_CONSENT_ENABLED": "true",
                "OPENAI_API_KEY": "test",
            },
        )


def test_illustration_rejects_insecure_storage():
    env = {
        "LL_AI_PRODUCTION_ENABLED": "true",
        "LL_ILLUSTRATION_ENABLED": "true",
        "LL_IMAGE_AI_CONSENT_ENABLED": "true",
        "OPENAI_API_KEY": "test",
        "LITTLE_LEGEND_ART_S3_ENDPOINT": "http://localhost",
        "LITTLE_LEGEND_ART_S3_BUCKET": "bucket",
        "LITTLE_LEGEND_ART_S3_REGION": "region",
        "LITTLE_LEGEND_ART_S3_ACCESS_KEY": "access",
        "LITTLE_LEGEND_ART_S3_SECRET_KEY": "secret",
        "LL_ILLUSTRATION_PRICE_MICRO_USD": "1000",
    }
    with pytest.raises(PermissionError, match="HTTPS"):
        runner.validate_ai_production(mode="illustration", env=env)


@pytest.mark.asyncio
async def test_writer_idle_does_not_trigger_busy_poll(monkeypatch):
    monkeypatch.setattr(
        runner, "execute_one_job", AsyncMock(return_value={"status": "idle"}),
    )
    assert await runner.process_cycle("writer") is False


@pytest.mark.asyncio
async def test_illustration_dispatches_one_queued_job(monkeypatch):
    task = AsyncMock(return_value=True)
    monkeypatch.setattr(runner, "execute_one_illustration", task)
    assert await runner.process_cycle("illustration") is True
    task.assert_awaited_once()


@pytest.mark.asyncio
async def test_once_does_not_repeat_provider_dispatch(monkeypatch):
    task = AsyncMock(return_value=True)
    monkeypatch.setattr(runner, "validate_ai_production", lambda **_: None)
    monkeypatch.setattr(runner, "process_cycle", task)
    await runner.run(mode="illustration", once=True)
    task.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_propagates(monkeypatch):
    import asyncio

    monkeypatch.setattr(runner, "validate_ai_production", lambda **_: None)
    monkeypatch.setattr(
        runner, "process_cycle", AsyncMock(side_effect=asyncio.CancelledError),
    )
    with pytest.raises(asyncio.CancelledError):
        await runner.run(mode="writer", once=True)
