"""Release deployment checks for Little Legend's dedicated worker."""
from unittest.mock import AsyncMock

import pytest

from app.little_legend import paid_book_worker


def test_worker_requires_private_storage_configuration(monkeypatch):
    monkeypatch.delenv("LITTLE_LEGEND_S3_BUCKET", raising=False)
    with pytest.raises(RuntimeError, match="Missing Little Legend worker settings"):
        paid_book_worker.check_worker_configuration()


def test_worker_rejects_plain_http_s3(monkeypatch):
    monkeypatch.setenv("LITTLE_LEGEND_S3_ENDPOINT", "http://example.invalid")
    with pytest.raises(RuntimeError, match="must use HTTPS"):
        paid_book_worker.check_worker_configuration()


@pytest.mark.asyncio
async def test_worker_survives_transient_cycle_error(monkeypatch):
    from asyncio import CancelledError

    attempts = 0

    async def process():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("temporary Neon outage")
        raise CancelledError()

    monkeypatch.setattr(paid_book_worker, "check_worker_configuration", lambda: None)
    monkeypatch.setattr(paid_book_worker, "process_one", process)
    monkeypatch.setattr(paid_book_worker.asyncio, "sleep", AsyncMock())
    with pytest.raises(CancelledError):
        await paid_book_worker.main()
    assert attempts == 2
