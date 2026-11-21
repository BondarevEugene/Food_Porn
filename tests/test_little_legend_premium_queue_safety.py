"""Premium queue preflight must reject stale and cross-owner art batches."""
import pytest

from app.little_legend.premium_batch_manifest import build_premium_batch_manifest
from app.little_legend.premium_queue_safety import (
    premium_story_fingerprint,
    require_premium_batch_ready,
)
from app.little_legend.premium_visual_contract import BookGenre, build_visual_plan
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def _data():
    graph = build_graph(["Forest discovery", "Mountain rescue"])
    manuscript = StoryManuscript(
        hero_name="Марта", parent_approved=True,
        chapters=[
            ChapterDraft(scene_id="scene_1", text="A story", approved=True, revision=2),
            ChapterDraft(scene_id="scene_2", text="Another story", approved=True, revision=3),
        ],
    )
    plan = build_visual_plan(
        genre=BookGenre.FAIRY_TALE, reference_ids=["a", "b", "c"],
        chapter_moments=[("Forest gate", "Forest clearing"),
                         ("Mountain trail", "Mountain summit")],
    )
    manifest = build_premium_batch_manifest(
        owner_id=7, story_id=11, plan=plan, chapter_revisions=[2, 3],
    )
    return dict(
        owner_id=7, story_id=11, graph=graph, manuscript=manuscript,
        plan=plan, manifest=manifest,
    )


def test_valid_batch_fingerprint_covers_full_story():
    data = _data()
    fingerprint = require_premium_batch_ready(**data)
    assert fingerprint == premium_story_fingerprint(
        graph=data["graph"], manuscript=data["manuscript"],
    )
    data["manuscript"].chapters[0].text = "Rewritten without revision bump"
    assert require_premium_batch_ready(**data) != fingerprint


@pytest.mark.parametrize("change", [
    "owner", "revision", "approval", "missing", "wrong_reference", "cover",
    "scene", "genre", "review",
])
def test_stale_or_incomplete_premium_batch_fails_closed(change):
    data = _data()
    if change == "owner":
        data["owner_id"] = 8
    elif change == "revision":
        data["manuscript"].chapters[0].revision = 9
    elif change == "approval":
        data["manuscript"].parent_approved = False
    elif change == "missing":
        data["manuscript"].chapters.pop()
    elif change == "wrong_reference":
        data["manifest"].requests[1].reference_id = "other"
    elif change == "cover":
        data["manifest"].requests[0].expected_revision = 0
    elif change == "scene":
        data["manifest"].requests[2].scene_description = "Unapproved scene"
    elif change == "genre":
        data["manifest"].genre = "detective"
    else:
        data["manifest"].requests[1].requires_identity_review = False
    with pytest.raises(PermissionError):
        require_premium_batch_ready(**data)
