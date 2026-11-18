"""No chapter may commit after consent or approval was revoked."""
from types import SimpleNamespace

import pytest

from app.little_legend.text_ai_consent import TextAIConsent
from app.little_legend.writer_result_commit import verify_commit_authorization


def draft(**overrides):
    data = {
        "text_ai_consent": TextAIConsent(),
        "outline_approved": True,
        "parent_sketch": object(),
        "graph": object(),
        "blueprint": SimpleNamespace(family_approved=True),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_missing_consent_blocks_commit():
    with pytest.raises(PermissionError, match="consent"):
        verify_commit_authorization(draft())


def test_withdrawn_outline_approval_blocks_commit(monkeypatch):
    monkeypatch.setattr(
        "app.little_legend.writer_result_commit.consent_allows_provider",
        lambda *_: True,
    )
    with pytest.raises(PermissionError, match="outline"):
        verify_commit_authorization(draft(outline_approved=False))


def test_unapproved_family_profile_blocks_commit(monkeypatch):
    monkeypatch.setattr(
        "app.little_legend.writer_result_commit.consent_allows_provider",
        lambda *_: True,
    )
    with pytest.raises(PermissionError, match="blueprint"):
        verify_commit_authorization(
            draft(blueprint=SimpleNamespace(family_approved=False))
        )
