"""Sensitive Telegram launch data must never appear in auth diagnostics."""
import logging

import pytest
from fastapi import HTTPException

from app.miniapp.auth import current_user, verify_init_data


def test_invalid_launch_signature_logs_reason_without_secrets(caplog):
    raw = "auth_date=100000&user=%7B%22id%22%3A11%7D&hash=" + "a" * 64
    with caplog.at_level(logging.WARNING, logger="app.miniapp.auth"):
        with pytest.raises(HTTPException) as raised:
            verify_init_data(raw, "123:private-token", now=100000)
    assert raised.value.status_code == 401
    assert "Invalid launch signature" in caplog.text
    assert "123:private-token" not in caplog.text
    assert "auth_date=" not in caplog.text
    assert "hash=" not in caplog.text


def test_missing_authorization_logs_category_without_secret(caplog):
    with caplog.at_level(logging.WARNING, logger="app.miniapp.auth"):
        with pytest.raises(HTTPException) as raised:
            current_user("")
    assert raised.value.status_code == 401
    assert "missing Authorization payload" in caplog.text
