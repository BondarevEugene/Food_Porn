"""Contract tests for the outbound OmniFactory CRM heartbeat agent."""
import asyncio
import hashlib
import hmac
import json
import time

import pytest

from app.services.omnifactory_fleet_agent import (
    FleetAgentConfig,
    FleetHeartbeatAgent,
    signed_heartbeat,
)


def test_heartbeat_matches_crm_ingest_hmac_contract():
    config = FleetAgentConfig(
        base_url="https://crm.example.org",
        bot_key="food_porn",
        ingest_secret="a-secure-shared-secret-at-least-24",
        runtime_version="food-porn-1.2.3",
    )
    config.validate()
    raw, headers = signed_heartbeat(config)
    payload = json.loads(raw)
    assert payload["type"] == "bot.heartbeat"
    assert payload["data"] == {"runtime_version": "food-porn-1.2.3"}
    assert payload["event_id"].startswith("fleet-")
    assert abs(time.time() - int(headers["X-Timestamp"])) < 5
    expected = hmac.new(
        config.ingest_secret.encode(),
        headers["X-Timestamp"].encode() + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    assert hmac.compare_digest(expected, headers["X-Signature"])
    assert "token" not in raw.decode().lower()


@pytest.mark.parametrize("config", [
    FleetAgentConfig(base_url="http://crm.example.org", bot_key="food_porn",
                     ingest_secret="a-secure-shared-secret-at-least-24"),
    FleetAgentConfig(base_url="https://crm.example.org", bot_key="food_porn"),
    FleetAgentConfig(base_url="https://user@crm.example.org", bot_key="food_porn",
                     ingest_secret="a-secure-shared-secret-at-least-24"),
])
def test_invalid_configuration_fails_closed(config):
    with pytest.raises(ValueError):
        config.validate()


@pytest.mark.asyncio
async def test_opt_in_and_graceful_shutdown():
    received = []

    async def sender(url, raw, headers):
        received.append((url, json.loads(raw), headers))

    disabled = FleetHeartbeatAgent(FleetAgentConfig(), sender=sender)
    assert await disabled.check_once() is False
    await disabled.start()
    assert disabled._task is None

    enabled = FleetHeartbeatAgent(
        FleetAgentConfig(base_url="https://crm.example.org", bot_key="food_porn",
                         ingest_secret="a-secure-shared-secret-at-least-24",
                         interval_seconds=30),
        sender=sender,
    )
    assert await enabled.check_once() is True
    assert received[0][0] == "https://crm.example.org/api/v1/events"
    await enabled.start()
    await asyncio.sleep(0)
    await enabled.stop()
    assert enabled._task is None
