"""Art snapshots must change when approved visual instructions change."""
from app.little_legend.art_dispatch_snapshot import art_dispatch_fingerprint
from app.little_legend.blueprint import BookBlueprint, CharacterProfile
from app.little_legend.character_identity import IdentityBible, VisualIdentity
from app.little_legend.router import StoryDraft
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def sample():
    graph = build_graph(["Марта в саду"])
    scene = graph.nodes[0]
    draft = StoryDraft(
        hero="Марта", graph=graph,
        blueprint=BookBlueprint(characters=[
            CharacterProfile(name="Марта", role="hero", appearance="Кудри"),
        ]),
        manuscript=StoryManuscript(
            hero_name="Марта", parent_approved=True,
            chapters=[ChapterDraft(
                scene_id=scene.id, text="Сад", approved=True,
            )],
        ),
    )
    return draft, scene.id


def test_snapshot_is_deterministic():
    draft, scene_id = sample()
    assert art_dispatch_fingerprint(draft, scene_id) == art_dispatch_fingerprint(
        draft, scene_id,
    )
    assert len(art_dispatch_fingerprint(draft, scene_id)) == 64


def test_scene_edit_changes_snapshot_without_revision_bump():
    draft, scene_id = sample()
    original = art_dispatch_fingerprint(draft, scene_id)
    draft.graph.nodes[0].illustration_prompt = "Новый ракурс"
    assert art_dispatch_fingerprint(draft, scene_id) != original


def test_reviewed_identity_edit_changes_snapshot():
    draft, scene_id = sample()
    draft.identity_bible = IdentityBible(
        hero_name="Марта", identity=VisualIdentity(
            parent_reviewed_description=True, hair="Кудри",
        ),
    )
    original = art_dispatch_fingerprint(draft, scene_id)
    draft.identity_bible.identity.hair = "Прямые волосы"
    assert art_dispatch_fingerprint(draft, scene_id) != original


def test_unreviewed_identity_is_not_sent_or_fingerprinted():
    draft, scene_id = sample()
    draft.identity_bible = IdentityBible(
        hero_name="Марта", identity=VisualIdentity(hair="Неутверждено"),
    )
    original = art_dispatch_fingerprint(draft, scene_id)
    draft.identity_bible.identity.hair = "Другая неутверждённая деталь"
    assert art_dispatch_fingerprint(draft, scene_id) == original


def test_style_and_approval_changes_invalidate_snapshot():
    draft, scene_id = sample()
    original = art_dispatch_fingerprint(draft, scene_id)
    draft.manuscript.parent_approved = False
    assert art_dispatch_fingerprint(draft, scene_id) != original


def test_chapter_revision_changes_snapshot():
    draft, scene_id = sample()
    original = art_dispatch_fingerprint(draft, scene_id)
    draft.manuscript.chapters[0].revision += 1
    assert art_dispatch_fingerprint(draft, scene_id) != original
