"""Provider receipts must be complete and effect keys must be deterministic."""
import pytest

from app.little_legend.production_effect_ledger import EffectKind
from app.little_legend.worker_charge_receipts import (
    validate_provider_receipt,
    worker_effect_key,
)


def test_effect_key_is_stable_and_kind_scoped() -> None:
    writer = worker_effect_key(job_id="job-12345678", kind=EffectKind.WRITER_AI)
    assert writer == worker_effect_key(
        job_id="job-12345678", kind=EffectKind.WRITER_AI,
    )
    assert writer.startswith("llai:")
    assert writer != worker_effect_key(
        job_id="job-12345678", kind=EffectKind.ILLUSTRATION_AI,
    )


def test_receipt_absence_is_allowed_for_legacy_completion() -> None:
    assert not validate_provider_receipt(
        actual_micro_usd=None, provider_reference=None,
    )


@pytest.mark.parametrize(
    ("amount", "reference"),
    [
        (None, "provider-123"),
        (100, None),
        (-1, "provider-123"),
        (True, "provider-123"),
        (0, ""),
        (100, "x" * 161),
    ],
)
def test_partial_or_invalid_receipt_is_rejected(
    amount: int | None, reference: str | None,
) -> None:
    with pytest.raises(ValueError, match="receipt"):
        validate_provider_receipt(
            actual_micro_usd=amount, provider_reference=reference,
        )


def test_zero_cost_receipt_with_reference_is_valid() -> None:
    assert validate_provider_receipt(
        actual_micro_usd=0, provider_reference="provider-ack-123",
    )


def test_non_ai_effect_cannot_use_worker_key() -> None:
    with pytest.raises(ValueError, match="Paid worker"):
        worker_effect_key(
            job_id="job-12345678", kind=EffectKind.TELEGRAM_PDF,
        )
