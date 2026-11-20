"""Regression: completed art batches must advance; failed ones must stop."""
from app.little_legend.production_conductor import Stage, classify
from app.little_legend.router import StoryDraft
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import StoryManuscript


def approved_book():
    draft = StoryDraft(outline_approved=True)
    draft = draft.model_copy(update={
        "parent_sketch": object(),
        "graph": build_graph(["First scene", "Second scene"]),
        "manuscript": StoryManuscript(
            hero_name=draft.hero, parent_approved=True,
        ),
    })
    return draft


def test_completed_art_batch_advances_to_editorial():
    draft = approved_book()
    assert classify(
        draft, writer_count=0, art_count=2,
        art_statuses=["completed", "completed"],
    ) == Stage.WAITING_EDITORIAL


def test_partial_art_batch_still_processing():
    assert classify(
        approved_book(), writer_count=0, art_count=2,
        art_statuses=["completed", "running"],
    ) == Stage.ILLUSTRATING


def test_failed_art_batch_requires_manual_review():
    assert classify(
        approved_book(), writer_count=0, art_count=2,
        art_statuses=["completed", "failed"],
    ) == Stage.MANUAL_REVIEW


def test_missing_art_job_requires_manual_review():
    assert classify(
        approved_book(), writer_count=0, art_count=1,
        art_statuses=["completed"],
    ) == Stage.MANUAL_REVIEW


def test_extra_art_job_requires_manual_review():
    assert classify(
        approved_book(), writer_count=0, art_count=3,
        art_statuses=["completed", "completed", "completed"],
    ) == Stage.MANUAL_REVIEW


def test_unknown_art_state_fails_closed():
    assert classify(
        approved_book(), writer_count=0, art_count=2,
        art_statuses=["completed", "uncertain"],
    ) == Stage.MANUAL_REVIEW
