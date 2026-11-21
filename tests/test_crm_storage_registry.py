"""Multibot storage registry contracts and namespace isolation."""
import json
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from app.crm.r2_storage import inventory
from app.crm.storage_registry import extra_connections


def registry_env(*, prefix="bot-a/", bot="bot_a"):
    env = {
        "ENDPOINT_URL": "https://r2.example.test",
        "BUCKET_NAME": "shared-private",
        "REGION_NAME": "auto",
        "ACCESS_KEY": "private",
        "SECRET_KEY": "private",
    }
    env["CRM_STORAGE_CONNECTIONS_JSON"] = json.dumps([{
        "bot_id": bot, "name": "assets", "prefix": prefix,
        "endpoint_env": "ENDPOINT_URL", "bucket_env": "BUCKET_NAME",
        "region_env": "REGION_NAME", "access_env": "ACCESS_KEY",
        "secret_env": "SECRET_KEY",
    }])
    return env


def test_registry_reads_secrets_from_environment_not_json():
    targets = extra_connections(registry_env())
    assert targets[0]["bot_id"] == "bot_a"
    assert targets[0]["prefix"] == "bot-a/"
    assert targets[0]["configured"] is True


def test_registry_rejects_overlapping_shared_bucket_prefixes():
    env = registry_env()
    entries = json.loads(env["CRM_STORAGE_CONNECTIONS_JSON"])
    entries.append({**entries[0], "bot_id": "bot_b", "prefix": "bot-a/books/"})
    env["CRM_STORAGE_CONNECTIONS_JSON"] = json.dumps(entries)
    with pytest.raises(ValueError, match="Overlapping"):
        extra_connections(env)


def test_registry_rejects_embedded_credentials_and_bad_prefix():
    env = registry_env(prefix="../")
    with pytest.raises(ValueError):
        extra_connections(env)
    env = registry_env()
    entries = json.loads(env["CRM_STORAGE_CONNECTIONS_JSON"])
    entries[0]["secret_env"] = "literal-secret-value"
    env["CRM_STORAGE_CONNECTIONS_JSON"] = json.dumps(entries)
    with pytest.raises(ValueError):
        extra_connections(env)


def test_inventory_uses_bot_specific_prefix():
    client = Mock()
    client.list_objects_v2.return_value = {
        "Contents": [{
            "Key": "bot-a/orders/one.pdf", "Size": 1024,
            "LastModified": datetime(2026, 11, 21, tzinfo=UTC),
        }], "IsTruncated": False,
    }
    with patch("app.crm.r2_storage.client_for", return_value=client):
        result = inventory(env=registry_env())
    assert result["bots"] == [{"id": "bot_a", "label": "Bot A"}]
    assert result["total_used_bytes"] == 1024
    assert client.list_objects_v2.call_args.kwargs["Prefix"] == "bot-a/"
