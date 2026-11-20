"""Privacy and structural checks for Little Legend manuscript quality gate."""
from app.little_legend.manuscript_quality import manuscript_quality_report
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def test_missing_manuscript_reports_no_private_data():
    report = manuscript_quality_report(build_graph(["Начало", "Конец"]), None)
    assert report["issue_counts"]["CHAPTER_MISSING"] == 2
    assert report["issue_counts"]["PARENT_APPROVAL_REQUIRED"] == 1
    assert report["ready_for_editorial_human_review"] is False
    assert report["ready_for_publication"] is False


def test_approved_chapters_pass_structural_checks():
    graph = build_graph(["Начало", "Конец"])
    prose = ("Герой нашёл старую карту и решил отправиться в путь. "
             "Он собрал друзей и проверил свой компас. "
             "На рассвете они вышли из дома.\n"
             "По дороге друзья помогали друг другу. " * 5)
    manuscript = StoryManuscript(
        hero_name="Герой",
        chapters=[
            ChapterDraft(scene_id=node.id, text=prose + str(node.order), approved=True)
            for node in graph.nodes
        ],
        parent_approved=True,
    )
    report = manuscript_quality_report(graph, manuscript)
    assert report["completed_scenes"] == 2
    assert report["ready_for_editorial_human_review"] is True
    assert report["semantic_quality_verified"] is False
    assert prose not in str(report)


def test_unapproved_short_and_repeated_openings_are_flagged():
    graph = build_graph(["Начало", "Конец"])
    manuscript = StoryManuscript(
        hero_name="Герой",
        chapters=[
            ChapterDraft(scene_id=node.id, text="Однажды началось приключение.")
            for node in graph.nodes
        ],
    )
    report = manuscript_quality_report(graph, manuscript)
    assert report["issue_counts"]["CHAPTER_TOO_SHORT"] == 2
    assert report["issue_counts"]["REPEATED_CHAPTER_OPENING"] == 1
    assert report["ready_for_editorial_human_review"] is False


def test_quality_ui_and_owner_only_endpoint():
    from app.little_legend.router import STUDIO_HTML

    assert "openManuscriptQuality()" in STUDIO_HTML
    assert "/manuscript-quality" in STUDIO_HTML
    assert "qualityScenes" in STUDIO_HTML
