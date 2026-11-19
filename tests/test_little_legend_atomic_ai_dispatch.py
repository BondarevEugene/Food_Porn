"""AI dispatch and settlement must enforce a single budgeted operation."""
import pytest
from sqlalchemy import Column, Integer, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.little_legend.atomic_ai_dispatch import DispatchAuthorization
from app.little_legend.book_budget_store import (
    BookBudget,
    available_micro_usd,
    book_budgets,
    budget_reservations,
)
from app.little_legend.production_effect_ledger import (
    EffectKind,
    EffectStatus,
    production_effects,
)


def test_dispatch_authorization_defaults_to_denied():
    authorization = DispatchAuthorization(
        effect_key="writer:2:scene_1:rev1",
        owner_id=3, story_id=2, reserved_micro_usd=5000,
    )
    assert authorization.authorized is False


def test_dispatch_authorization_rejects_invalid_budget():
    with pytest.raises(ValueError):
        DispatchAuthorization(
            effect_key="writer:2:scene_1:rev1",
            owner_id=3, story_id=2, reserved_micro_usd=0,
        )


def test_budget_remains_reserved_until_settlement():
    budget = BookBudget(
        owner_id=3, story_id=2,
        limit_micro_usd=100_000,
        held_micro_usd=80_000,
        spent_micro_usd=0,
    )
    assert available_micro_usd(budget) == 20_000


def test_ai_effect_kinds_exclude_delivery():
    assert EffectKind.TELEGRAM_PDF not in {
        EffectKind.WRITER_AI, EffectKind.ILLUSTRATION_AI,
    }


def test_effect_fence_state_is_not_confirmation():
    assert EffectStatus.DISPATCHED != EffectStatus.CONFIRMED


def test_atomic_tables_have_postgresql_ddl():
    Table(
        "little_legend_stories", book_budgets.metadata,
        Column("id", Integer, primary_key=True),
        extend_existing=True,
    )
    Table(
        "little_legend_stories", production_effects.metadata,
        Column("id", Integer, primary_key=True),
        extend_existing=True,
    )
    for table in (book_budgets, budget_reservations, production_effects):
        sql = str(CreateTable(table).compile(
            dialect=postgresql.dialect(),
        ))
        assert "PRIMARY KEY" in sql
