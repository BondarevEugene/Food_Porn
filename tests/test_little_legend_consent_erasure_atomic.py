"""Regression guard for atomic withdrawal and private erasure queue."""
from pathlib import Path

from app.little_legend.secure_vault import AssetState


def test_withdrawal_queues_erasure_in_same_database_transaction():
    source = Path("app/little_legend/router.py").read_text(encoding="utf-8")
    start = source.index('current.consent = withdraw_photo_consent(current.consent)')
    end = source.index('@router.get("/api/stories/{story_id}/vault-summary")', start)
    handler = source[start:end]
    queue = handler.index("await request_story_asset_erasure(")
    save = handler.index("await session.execute(update(stories)")
    commit = handler.index("await session.commit()")
    assert queue < save < commit
    assert '"physical_erasure_confirmed": False' in handler
    assert '"private_assets_queued_for_erasure": queued_for_erasure' in handler


def test_private_erasure_state_is_distinct_from_physical_deletion():
    assert AssetState.DELETION_PENDING != AssetState.DELETED
    assert AssetState.DELETE_FAILED != AssetState.DELETED


def test_customer_ui_does_not_claim_immediate_erasure():
    source = Path("app/little_legend/router.py").read_text(encoding="utf-8")
    assert "Физическое удаление ещё не подтверждено" in source
