"""Deterministic premium visual planning tests; no media or AI providers."""
import pytest
from pydantic import ValidationError

from app.little_legend.premium_visual_contract import (
    GENRE_DESIGNS,
    BookGenre,
    BookVisualPlan,
    build_visual_plan,
)


def test_three_references_cycle_across_twelve_chapters():
    moments = [
        (f"Chapter {i}: discovery", f"Chapter {i}: consequence")
        for i in range(1, 13)
    ]
    plan = build_visual_plan(
        genre=BookGenre.EPIC_FANTASY,
        reference_ids=["photo-a", "photo-b", "photo-c"],
        chapter_moments=moments,
    )
    assert len(plan.illustrations) == 24
    assert [slot.source_reference_id for slot in plan.illustrations[:8]] == [
        "photo-a", "photo-b", "photo-c", "photo-a",
        "photo-b", "photo-c", "photo-a", "photo-b",
    ]
    assert len({slot.moment_id for slot in plan.illustrations}) == 24
    assert all(slot.character_identity_required for slot in plan.illustrations)
    assert all(slot.full_head_safe_margin_required for slot in plan.illustrations)
    assert all(not slot.reuse_generated_art for slot in plan.illustrations)
    assert plan.cover_reference_id == "photo-a"
    assert plan.cover_character_identity_required


def test_story_background_and_costume_are_independent_of_reference_rotation():
    plan = build_visual_plan(
        genre=BookGenre.EPIC_FANTASY,
        reference_ids=["same-face"],
        chapter_moments=[("Find a map", "Meet a wolf")],
        costume_directions=["ordinary sweater", "embroidered cloak"],
        background_directions=["attic", "snowy forest"],
    )
    first, second = plan.illustrations
    assert first.source_reference_id == second.source_reference_id
    assert first.scene_description != second.scene_description
    assert first.costume_direction == "ordinary sweater"
    assert second.costume_direction == "embroidered cloak"
    assert first.background_direction == "attic"
    assert second.background_direction == "snowy forest"


@pytest.mark.parametrize("genre", list(BookGenre))
def test_every_genre_has_a_complete_distinct_design(genre):
    plan = build_visual_plan(
        genre=genre, reference_ids=["photo"],
        chapter_moments=[("First scene", "Second scene")],
    )
    assert plan.design == GENRE_DESIGNS[genre]
    assert plan.design.body_font_family
    assert plan.design.paper_texture
    assert plan.design.cover_material
    assert plan.design.bookmark_style
    assert plan.design.ink_color.startswith("#")


@pytest.mark.parametrize(
    ("references", "moments"),
    [
        ([], [("a", "b")]),
        ([""], [("a", "b")]),
        (["a", "a"], [("a", "b")]),
        (["a"], []),
        (["a"], [("a", "")]),
        (["a"], [("same", "same")]),
    ],
)
def test_invalid_inputs_fail_closed(references, moments):
    with pytest.raises(ValueError):
        build_visual_plan(
            genre=BookGenre.EPIC_FANTASY,
            reference_ids=references,
            chapter_moments=moments,
        )


def test_rejects_missing_or_duplicate_illustration_slots():
    plan = build_visual_plan(
        genre=BookGenre.EPIC_FANTASY,
        reference_ids=["a"], chapter_moments=[("one", "two")],
    )
    with pytest.raises(ValidationError):
        BookVisualPlan.model_validate(
            {**plan.model_dump(), "illustrations": plan.model_dump()["illustrations"][:1]}
        )
    duplicates = [plan.illustrations[0].model_dump()] * 2
    with pytest.raises(ValidationError):
        BookVisualPlan.model_validate(
            {**plan.model_dump(), "illustrations": duplicates}
        )
