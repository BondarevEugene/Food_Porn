"""Editorial approval must never be inferred from literal name matches."""
from app.little_legend.editorial_review import EditorialDecision, editorial_preflight
from app.little_legend.hero_contract import HeroContract
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def test_name_mentions_do_not_bypass_human_review():
    graph = build_graph(["Начало"])
    manuscript = StoryManuscript(
        hero_name="Марта", parent_approved=True,
        chapters=[ChapterDraft(
            scene_id=graph.nodes[0].id,
            text="Марта открыла дверь.", approved=True,
        )],
    )
    contract = HeroContract(hero_name="Марта", family_approved=True)
    report = editorial_preflight(
        manuscript, graph, contract, EditorialDecision(),
    )
    assert report["ready_for_print_proof"] is False
    assert report["ready_for_publication"] is False


def test_all_explicit_reviews_allow_print_proof_not_publication():
    graph = build_graph(["Начало"])
    manuscript = StoryManuscript(
        hero_name="Марта", parent_approved=True,
        chapters=[ChapterDraft(
            scene_id=graph.nodes[0].id,
            text="Марта открыла дверь.", approved=True,
        )],
    )
    contract = HeroContract(hero_name="Марта", family_approved=True)
    decision = EditorialDecision(
        hero_fidelity_reviewed=True,
        age_appropriateness_reviewed=True,
        narrative_continuity_reviewed=True,
        parent_final_approval=True,
    )
    report = editorial_preflight(manuscript, graph, contract, decision)
    assert report["ready_for_print_proof"] is True
    assert report["ready_for_publication"] is False


def test_mismatched_hero_blocks_review():
    graph = build_graph(["Начало"])
    manuscript = StoryManuscript(
        hero_name="Другой", parent_approved=True,
        chapters=[ChapterDraft(
            scene_id=graph.nodes[0].id,
            text="Марта открыла дверь.", approved=True,
        )],
    )
    report = editorial_preflight(
        manuscript, graph,
        HeroContract(hero_name="Марта", family_approved=True),
        EditorialDecision(
            hero_fidelity_reviewed=True,
            age_appropriateness_reviewed=True,
            narrative_continuity_reviewed=True,
            parent_final_approval=True,
        ),
    )
    assert report["ready_for_print_proof"] is False
