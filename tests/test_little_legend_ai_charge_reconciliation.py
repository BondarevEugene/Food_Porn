"""Unknown AI charges must not be released or retried automatically."""
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.little_legend.ai_charge_reconciliation import (
    PendingAICharge,
    reconcile_verified_ai_charge,
)
from app.little_legend.book_budget_store import BookBudget, available_micro_usd
from app.little_legend.production_effect_ledger import EffectKind, EffectStatus


def test_pending_charge_is_metadata_only():
    pending = PendingAICharge(
        effect_key="llai:12345678", story_id=12,
        kind=EffectKind.WRITER_AI, status=EffectStatus.UNCERTAIN,
        reserved_micro_usd=7500, updated_at=datetime.now(UTC),
    )
    assert "prompt" not in pending.model_fields
    assert "child_photo" not in pending.model_fields


def test_pending_charge_requires_positive_reservation():
    with pytest.raises(ValidationError):
        PendingAICharge(
            effect_key="llai:12345678", story_id=12,
            kind=EffectKind.ILLUSTRATION_AI,
            status=EffectStatus.DISPATCHED,
            reserved_micro_usd=0, updated_at=datetime.now(UTC),
        )


def test_unknown_charge_reduces_available_budget():
    budget = BookBudget(
        owner_id=4, story_id=12, limit_micro_usd=10000,
        held_micro_usd=7500, spent_micro_usd=0,
    )
    assert available_micro_usd(budget) == 2500


@pytest.mark.asyncio
async def test_unverified_receipt_is_rejected_before_database_access():
    with pytest.raises(PermissionError, match="verified"):
        await reconcile_verified_ai_charge(
            owner_id=4, story_id=12, effect_key="llai:12345678",
            actual_micro_usd=7000, provider_reference="receipt-123",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [-1, 1.5, True])
async def test_invalid_actual_charge_is_rejected(amount):
    with pytest.raises(ValueError):
        await reconcile_verified_ai_charge(
            owner_id=4, story_id=12, effect_key="llai:12345678",
            actual_micro_usd=amount, provider_reference="receipt-123",
            verified=True,
        )


@pytest.mark.asyncio
async def test_empty_provider_receipt_is_rejected():
    with pytest.raises(ValueError):
        await reconcile_verified_ai_charge(
            owner_id=4, story_id=12, effect_key="llai:12345678",
            actual_micro_usd=5000, provider_reference="",
            verified=True,
        )
