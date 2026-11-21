"""Premium claim and paid dispatch use separate, fail-closed paths."""
import inspect

from app.little_legend.premium_dispatch_store import (
    claim_next_premium_illustration_job,
    fence_premium_illustration_dispatch,
)


def test_premium_claim_skips_legacy_and_uses_leases():
    source = inspect.getsource(claim_next_premium_illustration_job)
    assert "if not job.premium_manifest_fingerprint" in source
    assert "claim_job(" in source
    assert "with_for_update(skip_locked=True)" in source
    assert "await session.commit()" in source


def test_paid_dispatch_rechecks_live_approvals_and_identity():
    source = inspect.getsource(fence_premium_illustration_dispatch)
    for required in (
        "job.lease_token != token",
        "job.provider_dispatched_at is not None",
        "manifest.fingerprint != job.premium_manifest_fingerprint",
        "require_book_art_ready(draft)",
        "require_premium_batch_ready(",
        "current_fingerprint != job.premium_story_fingerprint",
        "consent_allows_image_ai(",
    ):
        assert required in source


def test_paid_dispatch_fence_commits_before_returning_job():
    source = inspect.getsource(fence_premium_illustration_dispatch)
    assert source.index("await fence_worker_ai_effect(") < source.index(
        "job = job.model_copy(update={\"provider_dispatched_at\": now})"
    ) < source.index("await session.commit()")
    assert source.index("await session.commit()") < source.index("return job")
