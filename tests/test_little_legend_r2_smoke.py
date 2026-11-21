"""R2 diagnostic tests never access the network or customer files."""
from io import BytesIO

import pytest

from app.little_legend.r2_smoke import (
    PREFIX,
    StorageTarget,
    main,
    probe_target,
    validate_target,
)


class FakeClient:
    def __init__(self, *, corrupt=False, fail_put=False):
        self.objects = {}
        self.deleted = []
        self.corrupt = corrupt
        self.fail_put = fail_put

    def put_object(self, *, Bucket, Key, Body, **kwargs):
        assert Key.startswith(PREFIX)
        assert kwargs["CacheControl"] == "private, no-store"
        if self.fail_put:
            raise RuntimeError("simulated ambiguous failure")
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket, Key):
        data = self.objects[(Bucket, Key)]
        return {"Body": BytesIO(b"corrupt" if self.corrupt else data)}

    def delete_object(self, *, Bucket, Key):
        self.deleted.append((Bucket, Key))
        self.objects.pop((Bucket, Key), None)


def _target():
    return StorageTarget(
        label="release", endpoint="https://example.invalid",
        bucket="private", region="auto", access="dummy", secret="dummy",
    )


def test_probe_roundtrip_and_cleanup():
    client = FakeClient()
    probe_target(_target(), client=client)
    assert client.objects == {}
    assert len(client.deleted) == 1


def test_probe_corruption_fails_and_cleans_up():
    client = FakeClient(corrupt=True)
    with pytest.raises(RuntimeError, match="integrity"):
        probe_target(_target(), client=client)
    assert client.objects == {}
    assert len(client.deleted) == 1


def test_ambiguous_upload_attempts_cleanup():
    client = FakeClient(fail_put=True)
    with pytest.raises(RuntimeError, match="ambiguous"):
        probe_target(_target(), client=client)
    assert len(client.deleted) == 1


def test_missing_credentials_fail_closed():
    target = StorageTarget("art", "https://example.invalid", "private", "auto", "", "")
    with pytest.raises(ValueError, match="art"):
        validate_target(target)


def test_cli_reports_missing_configuration_without_secrets(monkeypatch, capsys):
    monkeypatch.delenv("LITTLE_LEGEND_S3_ENDPOINT_URL", raising=False)
    assert main([]) == 2
    output = capsys.readouterr().out
    assert "CONFIG_MISSING" in output
    assert "https://" not in output


def test_paid_book_storage_uses_canonical_endpoint(monkeypatch):
    from app.little_legend import paid_book_storage

    monkeypatch.setenv("LITTLE_LEGEND_S3_ENDPOINT_URL", "https://example.invalid")
    monkeypatch.delenv("LITTLE_LEGEND_S3_ENDPOINT", raising=False)
    monkeypatch.setenv("LITTLE_LEGEND_S3_BUCKET", "private")
    monkeypatch.setenv("LITTLE_LEGEND_S3_REGION", "auto")
    monkeypatch.setenv("LITTLE_LEGEND_S3_ACCESS_KEY_ID", "dummy")
    monkeypatch.setenv("LITTLE_LEGEND_S3_SECRET_ACCESS_KEY", "dummy")
    import boto3

    calls = {}

    def fake_client(service, **kwargs):
        calls.update(kwargs)
        assert service == "s3"
        return FakeClient()

    monkeypatch.setattr(boto3, "client", fake_client)
    store = paid_book_storage.PaidBookStore()
    assert store.bucket == "private"
    assert calls["endpoint_url"] == "https://example.invalid"
