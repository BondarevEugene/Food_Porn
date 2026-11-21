"""Premium editorial diagnostics must be stable, private and non-billable."""
from app.little_legend.editorial_quality import audit_manuscript
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import (
    ChapterDraft,
    StoryManuscript,
    manuscript_review,
)


def _book(texts, *, approved=True):
    graph = build_graph([f"Scene {i}" for i in range(len(texts))])
    manuscript = StoryManuscript(
        hero_name="Герой",
        parent_approved=approved,
        chapters=[
            ChapterDraft(scene_id=node.id, text=text, approved=approved)
            for node, text in zip(graph.nodes, texts, strict=True)
        ],
    )
    return graph, manuscript


def test_short_chapter_flagged_without_ai_calls():
    graph, manuscript = _book(["Короткая глава."])
    report = audit_manuscript(graph, manuscript)
    assert report.requires_human_review
    assert report.word_count == 2
    assert [f.code for f in report.findings] == ["chapter_too_short"]


def test_duplicate_text_detected_across_scenes():
    text = " ".join(["Приключение"] * 90) + "."
    graph, manuscript = _book([text, text])
    report = audit_manuscript(graph, manuscript)
    assert any(f.code == "duplicate_chapter_text" for f in report.findings)


def test_long_sentence_and_dense_paragraph_detected():
    text = " ".join(["волшебство"] * 250) + "."
    graph, manuscript = _book([text])
    codes = {f.code for f in audit_manuscript(graph, manuscript).findings}
    assert {"long_sentence", "dense_paragraph"} <= codes


def test_review_exposes_advisory_report_without_changing_approval_gate():
    graph, manuscript = _book(["Сказка."])
    result = manuscript_review(manuscript, graph)
    assert result["structurally_approved"]
    assert not result["ready_for_publication"]
    assert result["editorial_quality"]["requires_human_review"]
    assert result["editorial_quality"]["findings"][0]["code"] == "chapter_too_short"


def test_missing_and_unapproved_chapters_reported():
    graph, manuscript = _book(["Глава первая.", "Глава вторая."], approved=False)
    manuscript.chapters.pop()
    codes = {f.code for f in audit_manuscript(graph, manuscript).findings}
    assert {"chapter_missing", "chapter_not_approved", "parent_approval_missing"} <= codes
