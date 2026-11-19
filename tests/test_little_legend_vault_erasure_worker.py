"""Safety checks for private-vault physical deletion."""
from datetime import timedelta
from unittest.mock import Mock

import pytest

from app.little_legend.vault_erasure_worker import (
    S3PrivateObjectDeleter,
    error_category,
    retry_delay,
    validate_private_key,
)


def test_only_private_randomized_keys_can_be_deleted():
    validate_private_key("little-legend/private/" + "a" * 48)
    for key in (
        "little-legend/private/../../other",
        "little-legend/generated/" + "a" * 48,
        "little-legend/private/" + "A" * 48,
        "little-legend/private/" + "a" * 47,
        "another-bucket/" + "a" * 48,
    ):
        with pytest.raises(PermissionError):
            validate_private_key(key)


def test_s3_adapter_uses_only_validated_private_bucket_and_key():
    client = Mock()
    client.get_bucket_versioning.return_value = {}
    client.delete_object.return_value = {
        "ResponseMetadata": {"HTTPStatusCode": 204},
    }
    deleter = S3PrivateObjectDeleter(client=client, bucket="private-test")
    key = "little-legend/private/" + "f" * 48
    deleter.delete_private_object(object_key=key)
    client.delete_object.assert_called_once_with(Bucket="private-test", Key=key)
    with pytest.raises(PermissionError):
        deleter.delete_private_object(object_key="public/avatar.jpg")
    assert client.delete_object.call_count == 1


def test_bucket_must_be_configured():
    with pytest.raises(ValueError, match="bucket"):
        S3PrivateObjectDeleter(client=Mock(), bucket=" ")


def test_retry_backoff_is_bounded():
    assert retry_delay(1) == timedelta(minutes=2)
    assert retry_delay(4) == timedelta(minutes=16)
    assert retry_delay(100) == timedelta(hours=24)
    with pytest.raises(ValueError):
        retry_delay(0)


def test_errors_are_redacted_before_database_persistence():
    assert error_category(PermissionError("secret")) == "access_denied"
    assert error_category(TimeoutError("secret")) == "storage_unavailable"
    assert error_category(RuntimeError("secret")) == "deletion_failed"


@pytest.mark.asyncio
async def test_invalid_batch_never_touches_database():
    from app.little_legend.vault_erasure_worker import erase_due_private_assets

    with pytest.raises(ValueError, match="batch_size"):
        await erase_due_private_assets(deleter=Mock(), batch_size=0)
    with pytest.raises(ValueError, match="batch_size"):
        await erase_due_private_assets(deleter=Mock(), batch_size=101)


def test_versioned_bucket_cannot_claim_physical_erasure():
    client = Mock()
    client.get_bucket_versioning.return_value = {"Status": "Enabled"}
    with pytest.raises(PermissionError, match="Versioned buckets"):
        S3PrivateObjectDeleter(client=client, bucket="versioned")
    client.delete_object.assert_not_called()


def test_unconfirmed_storage_response_cannot_mark_erasure():
    client = Mock()
    client.get_bucket_versioning.return_value = {}
    client.delete_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 500}}
    deleter = S3PrivateObjectDeleter(client=client, bucket="private-test")
    with pytest.raises(RuntimeError, match="not confirmed"):
        deleter.delete_private_object(object_key="little-legend/private/" + "a" * 48)
