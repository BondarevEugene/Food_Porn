"""Character identity review never enables photo processing."""
import pytest
from pydantic import ValidationError

from app.little_legend.blueprint import quick_blueprint
from app.little_legend.character_identity import (
    IdentityBible,
    VisualIdentity,
    identity_review,
    quick_identity_bible,
)
from app.little_legend.router import StoryDraft
from app.little_legend.story_graph import build_graph


def test_quick_bible_preserves_existing_hero_notes():
    blueprint = quick_blueprint("Оля", age=8)
    blueprint.characters[0].appearance = "Каштановые волосы"
    blueprint.characters[0].visual_identity_notes = "Три веснушки"
    bible = quick_identity_bible(blueprint, "Оля")
    assert "Каштановые волосы" in " ".join(bible.consistency_rules)
    assert "Три веснушки" in " ".join(bible.consistency_rules)


def test_portrait_approval_requires_parental_consent():
    with pytest.raises(ValidationError):
        VisualIdentity(portrait_review="approved")


def test_identity_review_cannot_enable_generation():
    bible = IdentityBible(
        hero_name="Оля",
        identity=VisualIdentity(
            hair="Каштановые волосы",
            parent_reviewed_description=True,
            parental_photo_consent=True,
            portrait_review="approved",
        ),
    )
    report = identity_review(bible, build_graph(["Начало", "Выбор"]))
    assert report["ready_for_photo_generation"] is False
    assert report["face_similarity_measured"] is False
    assert report["reference_storage_enabled"] is False
    assert len(report["scenes"]) == 2


def test_identity_bible_roundtrip_and_legacy_draft_compatibility():
    draft = StoryDraft(identity_bible=IdentityBible(
        hero_name="Оля", identity=VisualIdentity(eyes="Зелёные"),
    ))
    restored = StoryDraft.model_validate_json(draft.model_dump_json())
    assert restored.identity_bible.identity.eyes == "Зелёные"
    legacy = StoryDraft.model_validate({"hero": "Оля"})
    assert "identity_bible" not in legacy.model_fields_set
