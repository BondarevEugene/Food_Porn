"""Operator runner defaults to zero-cost and refuses incomplete setup."""
from unittest.mock import AsyncMock, patch

import pytest

from app.little_legend.writer_runner import (
    main,
    validate_operator_configuration,
)


def test_runner_dry_run_without_credentials(capsys):
    assert main([]) == 0
    assert "dry-run only" in capsys.readouterr().out


def test_execute_requires_explicit_opt_in():
    with pytest.raises(PermissionError, match="LL_WRITER_ENABLED"):
        validate_operator_configuration(
            execute=True, env={"OPENAI_API_KEY": "fake"},
        )


def test_execute_requires_key():
    with pytest.raises(PermissionError, match="OPENAI_API_KEY"):
        validate_operator_configuration(
            execute=True, env={"LL_WRITER_ENABLED": "true"},
        )


def test_execute_requires_disclosure():
    with pytest.raises(PermissionError, match="disclosure"):
        validate_operator_configuration(
            execute=True, env={
                "LL_WRITER_ENABLED": "true",
                "OPENAI_API_KEY": "fake",
            },
        )


def test_execute_one_job_only_and_no_prose_output(capsys, monkeypatch):
    monkeypatch.setenv("LL_WRITER_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("LL_TEXT_AI_CONSENT_ENABLED", "true")
    with patch(
        "app.little_legend.writer_runner.execute_one_job",
        new_callable=AsyncMock,
        return_value={"status": "completed", "text": "PRIVATE PROSE"},
    ) as worker:
        assert main(["--execute"]) == 0
    worker.assert_awaited_once()
    assert "PRIVATE PROSE" not in capsys.readouterr().out
