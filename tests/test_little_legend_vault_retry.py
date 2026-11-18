"""Deletion retry policy and schema contract."""
from datetime import timedelta

import pytest

from app.little_legend.deletion_worker import retry_delay
from app.little_legend.vault_registry import vault_assets


def test_exponential_backoff_is_bounded():
    assert retry_delay(1) == timedelta(minutes=5)
    assert retry_delay(2) == timedelta(minutes=10)
    assert retry_delay(3) == timedelta(minutes=20)
    assert retry_delay(20) == timedelta(hours=24)
    with pytest.raises(ValueError):
        retry_delay(0)


def test_retry_columns_are_registered():
    columns = vault_assets.c
    assert "last_deletion_attempt_at" in columns
    assert "next_deletion_attempt_at" in columns


def test_retry_index_exists():
    assert "ix_ll_vault_retry_due" in {
        index.name for index in vault_assets.indexes
    }
