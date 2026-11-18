"""Story manuscript planning and editorial gates."""
from app.little_legend.blueprint import quick_blueprint
from app.little_legend.hero_contract import contract_from_blueprint
from app.little_legend.manuscript_studio import (
    ChapterPlan,
    ManuscriptPlan,
    chapter_writing_jobs,
    manuscript_preflight,
)
from app.little_legend.narrative_design import StoryDesign
from app.little_legend.story_graph import build_graph


def test_chapter_jobs_preserve_hero_and_causality():
    blueprint = quick_blueprint("Марта", age=7)
    contract = contract_from_blueprint(blueprint, "Марта")
    jobs = chapter_writing_jobs(
        build_graph(["Начало", "Испытание", "Финал"]),
        contract, blueprint, StoryDesign(desire="Спасти друга"),
    )
    assert len(jobs) == 3
    assert all(job["hero_brief"]["hero"]["hero_name"] == "Марта" for job in jobs)
    assert jobs[1]["story_context"]["previous_scene"] == "Начало"
    assert jobs[1]["story_context"]["next_scene"] == "Финал"


def test_manuscript_never_claims_semantic_fidelity():
    blueprint = quick_blueprint("Марта")
    contract = contract_from_blueprint(blueprint, "Марта")
    graph = build_graph(["Начало"])
    plan = ManuscriptPlan(
        hero_name="Марта",
        chapters=[ChapterPlan(
            scene_id="scene_1", title="Начало", hero_action="Помогла",
            character_detail="Любознательность", emotional_change="Смелость",
            causal_link="Нашла ключ", manuscript="Марта нашла ключ.",
            parent_approved=True,
        )],
        parent_approved=True,
    )
    result = manuscript_preflight(plan, graph, contract)
    assert result["ready_for_publication"] is False
    assert result["semantic_fidelity_verified"] is False
    assert result["ready_for_editorial_review"] is False
