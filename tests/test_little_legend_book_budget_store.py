"""AI cost accounting must preserve book spending ceilings."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import Column, Integer, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.little_legend.book_budget_store import (
    BookBudget,
    _validate_amount,
    available_micro_usd,
    book_budgets,
    budget_reservations,
)


def test_available_budget_accounts_for_holds_and_spending():
    budget = BookBudget(
        owner_id=3, story_id=2,
        limit_micro_usd=1_000_000,
        held_micro_usd=250_000,
        spent_micro_usd=400_000,
    )
    assert available_micro_usd(budget) == 350_000


@pytest.mark.parametrize("amount", [0, -1, 1.5, True])
def test_invalid_reservation_amount_is_rejected(amount):
    with pytest.raises(ValueError):
        _validate_amount(amount)


def test_book_budget_validation_rejects_negative_cost():
    with pytest.raises(ValueError):
        BookBudget(
            owner_id=3, story_id=2,
            limit_micro_usd=100, held_micro_usd=-1,
            spent_micro_usd=0,
        )


def test_budget_schema_compiles_for_postgresql():
    Table(
        "little_legend_stories", book_budgets.metadata,
        Column("id", Integer, primary_key=True),
        extend_existing=True,
    )
    for table in (book_budgets, budget_reservations):
        sql = str(CreateTable(table).compile(
            dialect=postgresql.dialect(),
        ))
        assert "ON DELETE CASCADE" in sql
        assert "PRIMARY KEY" in sql


def test_budget_reservations_have_unique_effect_keys():
    assert budget_reservations.primary_key.columns.keys() == ["effect_key"]
    assert book_budgets.primary_key.columns.keys() == ["story_id"]
    assert budget_reservations.c.reserved_micro_usd.nullable is False


def test_budget_timestamp_column_is_timezone_aware():
    assert book_budgets.c.updated_at.type.timezone
    assert isinstance(datetime.now(UTC), datetime)
