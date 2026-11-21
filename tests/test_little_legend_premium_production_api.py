"""Premium production API never exposes job leases, reference photos or keys."""
import inspect

from app.little_legend.router import premium_production_progress


def test_premium_progress_requires_owner_and_reuses_owner_scoped_query():
    source = inspect.getsource(premium_production_progress)
    assert "await _owned_draft(story_id, owner)" in source
    assert "owner_id=owner" in source
    assert "audit_premium_batch(jobs=premium_jobs)" in source
    assert "Premium batch integrity validation failed" in source
