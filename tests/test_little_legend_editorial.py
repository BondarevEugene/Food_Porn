"""Editorial quality and director-mode regression checks."""
from app.little_legend.editorial import audit_story
from app.little_legend.router import STUDIO_HTML, StoryDraft
from app.little_legend.story_graph import build_graph


def test_editorial_audit_flags_unfinished_scenes():
    graph = build_graph(["", "Первое открытие", ""])
    report = audit_story(graph)
    assert report.publishable is False
    assert report.score < 100
    assert sum(issue.code == "missing_scene" for issue in report.issues) == 2
    assert sum(issue.code == "missing_conflict" for issue in report.issues) == 3


def test_editorial_audit_improves_with_scene_details():
    graph = build_graph(["Начало", "Середина", "Конец"])
    before = audit_story(graph).score
    for node in graph.nodes:
        node.conflict = "Препятствие"
        node.consequence = "Герой делает выбор"
    after = audit_story(graph)
    assert after.score > before
    assert after.issues == []


def test_legacy_draft_does_not_explicitly_supply_graph_or_blueprint():
    draft = StoryDraft.model_validate({
        "title": "Новая сказка", "hero": "Оля", "scenes": ["Сцена"]
    })
    assert "graph" not in draft.model_fields_set
    assert "blueprint" not in draft.model_fields_set


def test_director_ui_uses_safe_dom_operations():
    assert "saveGraph()" in STUDIO_HTML
    assert "node.locked" in STUDIO_HTML
    assert "textContent" in STUDIO_HTML
    assert "innerHTML" not in STUDIO_HTML
