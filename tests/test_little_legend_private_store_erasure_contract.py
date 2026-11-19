"""Regression tests for both private S3 deletion implementations."""
from unittest.mock import Mock, patch

import pytest

from app.little_legend.object_store import S3PrivateStore, S3Settings


def settings():
    return S3Settings(
        endpoint_url="https://s3.example.test",
        bucket="private-bucket",
        region="eu-central-1",
        access_key_id="test-access",
        secret_access_key="test-secret",
    )


def test_private_store_rejects_versioned_bucket():
    client = Mock()
    client.get_bucket_versioning.return_value = {"Status": "Enabled"}
    with patch("boto3.client", return_value=client):
        with pytest.raises(PermissionError, match="version-aware"):
            S3PrivateStore(settings())
    client.delete_object.assert_not_called()


def test_private_store_confirms_delete_before_success():
    client = Mock()
    client.get_bucket_versioning.return_value = {}
    client.delete_object.return_value = {
        "ResponseMetadata": {"HTTPStatusCode": 204},
    }
    with patch("boto3.client", return_value=client):
        store = S3PrivateStore(settings())
    key = "little-legend/private/" + "a" * 48
    store.delete(key=key)
    client.delete_object.assert_called_once_with(
        Bucket="private-bucket", Key=key,
    )


def test_private_store_rejects_unconfirmed_delete():
    client = Mock()
    client.get_bucket_versioning.return_value = {}
    client.delete_object.return_value = {
        "ResponseMetadata": {"HTTPStatusCode": 500},
    }
    with patch("boto3.client", return_value=client):
        store = S3PrivateStore(settings())
    with pytest.raises(RuntimeError, match="not confirmed"):
        store.delete(key="little-legend/private/" + "b" * 48)
