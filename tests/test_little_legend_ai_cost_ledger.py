"""Confirmed costs are distinct from estimated or dispatched costs."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.little_legend.ai_cost_ledger import CostEvidence, CostReceipt


def make_receipt(amount):
    return CostReceipt(
        receipt_id="receipt_12345678", job_id="writer_job_12345678",
        provider="example_provider", provider_reference="charge_12345678",
        amount_usd=amount, evidence=CostEvidence.PROVIDER_RECEIPT,
    )


def test_confirmed_cost_uses_exact_decimal():
    assert make_receipt("0.001234").amount_usd == Decimal("0.001234")


@pytest.mark.parametrize("amount", ["-0.01", "NaN", "Infinity", "0.1234567", "101"])
def test_invalid_confirmed_cost_rejected(amount):
    with pytest.raises(ValidationError):
        make_receipt(amount)


def test_receipt_requires_provider_reference():
    with pytest.raises(ValidationError):
        CostReceipt(
            receipt_id="receipt_12345678", job_id="writer_job_12345678",
            provider="example_provider", provider_reference="",
            amount_usd="0.01", evidence=CostEvidence.PROVIDER_RECEIPT,
        )
