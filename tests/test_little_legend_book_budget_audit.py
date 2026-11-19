"""Budget audit reports mismatches without modifying financial records."""
from app.little_legend.book_budget_audit import classify_budget_audit


def test_balanced_book_is_consistent() -> None:
    result = classify_budget_audit(
        story_id=1, owner_id=2,
        held_micro_usd=300, spent_micro_usd=500,
        recorded_held_micro_usd=300,
        recorded_spent_micro_usd=500, unresolved_effects=1,
    )
    assert result.consistent
    assert result.unresolved_effects == 1


def test_unbalanced_book_is_flagged() -> None:
    result = classify_budget_audit(
        story_id=1, owner_id=2,
        held_micro_usd=300, spent_micro_usd=500,
        recorded_held_micro_usd=200,
        recorded_spent_micro_usd=500, unresolved_effects=0,
    )
    assert not result.consistent


def test_negative_balance_is_flagged() -> None:
    result = classify_budget_audit(
        story_id=1, owner_id=2,
        held_micro_usd=-1, spent_micro_usd=0,
        recorded_held_micro_usd=-1,
        recorded_spent_micro_usd=0, unresolved_effects=0,
    )
    assert not result.consistent
