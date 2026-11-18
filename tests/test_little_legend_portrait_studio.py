"""Portrait Studio must remain metadata-only until privacy gates are complete."""
import pytest
from pydantic import ValidationError

from app.little_legend.character_identity import IdentityBible, VisualIdentity
from app.little_legend.consent import ConsentDecision, ConsentRecord, record_decision
from app.little_legend.portrait_studio import PortraitPlan, portrait_preflight
from app.little_legend.router import STUDIO_HTML, StoryDraft


def test_portrait_disabled_even_after_terms_acceptance():
    consent = record_decision(
        ConsentRecord(),
        ConsentDecision(accept_terms=True, declare_parental_authority=True),
    )
    bible = IdentityBible(
        hero_name="Оля",
        identity=VisualIdentity(
            hair="каштановые", eyes="карие", parent_reviewed_description=True
        ),
    )
    plan = PortraitPlan(parent_description_approved=True)
    report = portrait_preflight(plan, bible, consent)
    assert report["description_ready"] is True
    assert report["photo_upload_enabled"] is False
    assert report["portrait_generation_enabled"] is False
    assert report["face_similarity_measured"] is False
    assert report["blockers"]


def test_cannot_fake_review_of_reference_photo():
    with pytest.raises(ValidationError):
        PortraitPlan(reference_photo_reviewed=True)


def test_legacy_draft_and_ui():
    draft = StoryDraft.model_validate({"hero": "Оля"})
    assert draft.portrait_plan.mode == "quick"
    assert StoryDraft.model_validate_json(draft.model_dump_json()).portrait_plan.mode == "quick"
    assert 'id="portrait"' in STUDIO_HTML
    assert 'id="portraitApproved"' in STUDIO_HTML
    assert 'openPortrait()' in STUDIO_HTML


def test_director_options_and_bounds():
    plan = PortraitPlan(mode="director", framing="full-body", avoid=["no face crop"])
    assert plan.model_dump()["framing"] == "full-body"
    with pytest.raises(ValidationError):
        PortraitPlan(avoid=["x"] * 13)
