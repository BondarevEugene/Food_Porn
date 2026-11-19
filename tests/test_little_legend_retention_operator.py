"""One-shot retention operator command safety contracts."""
from unittest.mock import AsyncMock, patch

import pytest

from app.little_legend.retention_operator import _parser, run_operator


def test_cli_requires_explicit_mode():
    with pytest.raises(SystemExit):
        _parser().parse_args([])


def test_cli_rejects_conflicting_modes():
    with pytest.raises(SystemExit):
        _parser().parse_args(["--dry-run", "--execute"])


@pytest.mark.asyncio
async def test_execute_refuses_without_operator_approval(monkeypatch):
    monkeypatch.delenv("LITTLE_LEGEND_RETENTION_EXECUTE", raising=False)
    with pytest.raises(PermissionError, match="approval"):
        await run_operator(execute=True, batch_size=25)


@pytest.mark.asyncio
async def test_execute_rejects_invalid_batch_before_side_effects():
    with pytest.raises(ValueError, match="batch_size"):
        await run_operator(execute=True, batch_size=0)


@pytest.mark.asyncio
async def test_execute_requires_private_bucket(monkeypatch):
    monkeypatch.setenv("LITTLE_LEGEND_RETENTION_EXECUTE", "YES")
    monkeypatch.delenv("LITTLE_LEGEND_PRIVATE_BUCKET", raising=False)
    with patch("boto3.client") as client:
        with pytest.raises(ValueError, match="bucket"):
            await run_operator(execute=True, batch_size=25)
    client.assert_not_called()
