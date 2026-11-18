"""Customer-authored story material must reach every chapter brief."""
import pytest

from app.little_legend.blueprint import quick_blueprint
from app.little_legend.client_sketch import ParentSketch, outline_from_sketch
from app.little_legend.hero_contract import contract_from_blueprint
from app.little_legend.sketch_writer_briefs import (
    SketchWritingSettings,
    compose_sketch_chapter_briefs,
)
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def setup():
    sketch = ParentSketch(
        premise="Марта находит загадочную карту на чердаке.",
        moments=["Сова вручает ключ.", "Марта открывает башню."],
        avoid=["смерть персонажей"],
        special_choice="Марта делится находкой",
    )
    outline = outline_from_sketch(sketch, chapter_count=3)
    blueprint = quick_blueprint("Марта")
    blueprint.family_approved = True
    contract = contract_from_blueprint(blueprint, "Марта")
    return sketch, outline, blueprint, contract


def briefs(*, approved=True, existing=None):
    sketch, outline, blueprint, contract = setup()
    return compose_sketch_chapter_briefs(
        sketch=sketch, graph=outline.graph, contract=contract,
        blueprint=blueprint, design=outline.design,
        settings=SketchWritingSettings(), outline_approved=approved,
        existing=existing,
    )


def test_all_briefs_include_parent_source_and_safety_exclusions():
    result = briefs()
    assert len(result) == 3
    assert all("смерть персонажей" in b["parent_original"]["excluded_topics"]
               for b in result)
    assert all(b["hero_brief"]["approved_for_generation"] for b in result)
    assert all(b["parent_original"]["decisive_choice"] == "Марта делится находкой"
               for b in result)


def test_unapproved_outline_blocks_generation():
    with pytest.raises(PermissionError, match="outline"):
        briefs(approved=False)


def test_approved_chapter_is_not_rewritten():
    existing = StoryManuscript(
        hero_name="Марта",
        chapters=[ChapterDraft(
            scene_id="scene_1", text="Готовая глава", approved=True,
        )],
    )
    result = briefs(existing=existing)
    assert len(result) == 2
    assert all(b["scene_id"] != "scene_1" for b in result)


def test_bad_length_range_rejected():
    sketch, outline, blueprint, contract = setup()
    with pytest.raises(ValueError, match="length"):
        compose_sketch_chapter_briefs(
            sketch=sketch, graph=outline.graph, contract=contract,
            blueprint=blueprint, design=outline.design,
            settings=SketchWritingSettings(
                chapter_min_words=700, chapter_max_words=300,
            ), outline_approved=True,
        )
