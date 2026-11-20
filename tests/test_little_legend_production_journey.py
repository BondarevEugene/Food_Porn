"""Customer-safe paid production journey contracts."""
from app.little_legend.production_journey import JourneyStage, stage_for
from app.little_legend.router import StoryDraft
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import StoryManuscript


def view(draft=None, *, paid=True, status="pending", writers=(), art=(),
         delivery_started=False, delivered=False):
    return stage_for(
        draft=draft or StoryDraft(),
        payment_verified=paid,
        fulfillment_status=status,
        delivery_started=delivery_started,
        delivered=delivered,
        writers=list(writers),
        illustrations=list(art),
    )


def approved_draft(*, manuscript=False, image_consent=False):
    draft = StoryDraft(
        outline_approved=True,
        graph=build_graph(["Approved scene"]),
    )
    # Parent sketch data is not needed for a pure state-transition test.
    draft = draft.model_copy(update={"parent_sketch": object()})
    if manuscript:
        draft.manuscript = StoryManuscript(
            hero_name=draft.hero, parent_approved=True,
        )
    if image_consent:
        draft.image_ai_consent.active = True
    return draft


def test_payment_is_required_before_production():
    assert view(paid=False) == (
        JourneyStage.AWAITING_PAYMENT, "complete_payment",
    )


def test_parent_must_approve_outline():
    assert view() == (JourneyStage.AWAITING_OUTLINE, "approve_outline")


def test_writer_queue_is_visible_to_parent():
    draft = approved_draft()
    assert view(draft, writers=["queued"]) == (
        JourneyStage.WRITING, "wait",
    )
    assert view(draft, writers=["running"]) == (
        JourneyStage.WRITING, "wait",
    )


def test_completed_writer_job_waits_for_parent_review():
    assert view(approved_draft(), writers=["completed"]) == (
        JourneyStage.REVIEW_CHAPTERS, "approve_manuscript",
    )


def test_failed_writer_is_never_presented_as_success():
    assert view(approved_draft(), writers=["failed"]) == (
        JourneyStage.MANUAL_REVIEW, "contact_support",
    )


def test_parent_approved_manuscript_waits_for_image_consent():
    assert view(approved_draft(manuscript=True)) == (
        JourneyStage.AWAITING_IMAGE_CONSENT, "approve_image_ai",
    )


def test_illustration_generation_progress():
    draft = approved_draft(manuscript=True, image_consent=True)
    assert view(draft, art=["completed", "running"]) == (
        JourneyStage.ILLUSTRATING, "wait",
    )
    assert view(draft, art=["completed"]) == (
        JourneyStage.FINAL_REVIEW, "approve_final_book",
    )


def test_ambiguous_telegram_delivery_never_asks_to_resend():
    assert view(delivery_started=True) == (
        JourneyStage.MANUAL_REVIEW, "contact_support",
    )


def test_confirmed_receipt_is_delivered():
    assert view(delivered=True) == (
        JourneyStage.DELIVERED, "download_book",
    )


def test_blocked_fulfillment_requires_operator():
    assert view(status="blocked") == (
        JourneyStage.MANUAL_REVIEW, "contact_support",
    )
