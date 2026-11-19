"""A quote or client-provided payment status never grants production access."""
from app.little_legend.payment_entitlement import PaymentEvidence, evidence_matches_quote


def quote() -> dict:
    return {
        "id": 19,
        "owner_id": 42,
        "edition": "digital",
        "currency": "UAH",
        "price_minor": 129900,
        "status": "quoted",
    }


def evidence() -> PaymentEvidence:
    return PaymentEvidence(
        quote_id=19,
        owner_id=42,
        provider="wayforpay",
        provider_reference="fp_ll_19_abc",
        amount_minor=129900,
        currency="UAH",
    )


def test_matching_verified_evidence():
    assert evidence_matches_quote(evidence(), quote())


def test_mismatches_fail_closed():
    from dataclasses import replace

    original = evidence()
    for changed in (
        replace(original, quote_id=20),
        replace(original, owner_id=43),
        replace(original, provider="unknown"),
        replace(original, provider_reference=" "),
        replace(original, amount_minor=129901),
        replace(original, currency="USD"),
    ):
        assert not evidence_matches_quote(changed, quote())


def test_print_and_mutated_quote_cannot_grant_access():
    for key, value in (
        ("edition", "print"),
        ("status", "paid"),
        ("currency", "USD"),
        ("price_minor", 100),
        ("owner_id", 100),
    ):
        changed = quote()
        changed[key] = value
        assert not evidence_matches_quote(evidence(), changed)
