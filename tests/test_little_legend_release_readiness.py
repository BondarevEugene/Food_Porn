"""Paid release preflight rejects missing payment, approval and art."""
from app.little_legend.release_readiness import assess_paid_release
from app.little_legend.router import StoryDraft
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import StoryManuscript


def report(draft=None, *, paid=True, status="pending", art=None):
    return assess_paid_release(
        quote_id=12, draft=draft or StoryDraft(),
        payment_verified=paid, fulfillment_status=status,
        art_jobs=art or [],
    )


def approved_draft():
    draft = StoryDraft()
    draft = draft.model_copy(update={
        "graph": build_graph(["A scene"]),
        "manuscript": StoryManuscript(
            hero_name=draft.hero, parent_approved=True,
        ),
    })
    return draft


def test_payment_missing_blocks_release():
    result = report(paid=False)
    assert not result.release_ready
    assert "payment_not_verified" in result.blockers


def test_no_fulfillment_request_blocks_release():
    result = report(status=None)
    assert "fulfillment_not_requested" in result.blockers


def test_unapproved_story_has_actionable_blockers():
    result = report()
    assert not result.release_ready
    assert "graph_missing" in result.blockers
    assert "manuscript_missing" in result.blockers
    assert "final_parent_editorial_approval_missing" in result.blockers


def test_missing_art_blocks_even_with_final_approval():
    draft = approved_draft()
    draft.editorial_decision.hero_fidelity_reviewed = True
    draft.editorial_decision.age_appropriateness_reviewed = True
    draft.editorial_decision.narrative_continuity_reviewed = True
    draft.editorial_decision.parent_final_approval = True
    result = report(draft)
    assert not result.release_ready
    assert result.total_scenes == 1
    assert result.completed_scenes == 0
    assert "illustration_job_count_invalid" in result.blockers
    assert result.requires_manual_review


def test_blocked_fulfillment_never_claimed_ready():
    result = report(status="blocked")
    assert not result.release_ready
    assert result.requires_manual_review
    assert "fulfillment_blocked" in result.blockers


def test_unknown_fulfillment_state_fails_closed():
    result = report(status="unknown")
    assert not result.release_ready
    assert "fulfillment_state_unknown" in result.blockers


def test_blockers_are_deduplicated_and_stable():
    result = report()
    assert result.blockers == sorted(set(result.blockers))
