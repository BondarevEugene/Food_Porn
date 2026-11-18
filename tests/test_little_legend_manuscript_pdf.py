"""The editorial PDF must contain full prose and reject incomplete manuscripts."""
import pytest

from app.little_legend.manuscript_pdf import render_manuscript_proof
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def test_full_manuscript_pdf_is_generated():
    graph = build_graph(["Краткий план первой сцены", "Краткий план второй сцены"])
    manuscript = StoryManuscript(
        hero_name="Марта",
        chapters=[
            ChapterDraft(
                scene_id="scene_1",
                text="Марта открыла дверь.\n\nЗа дверью сиял сад.",
            ),
            ChapterDraft(
                scene_id="scene_2",
                text="И тогда Марта сделала свой выбор.",
            ),
        ],
    )
    pdf = render_manuscript_proof(
        title="Приключение Марты", dedication="С любовью",
        graph=graph, manuscript=manuscript,
    )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 2000


def test_missing_chapter_is_rejected_instead_of_using_outline():
    graph = build_graph(["Первая сцена", "Вторая сцена"])
    manuscript = StoryManuscript(
        hero_name="Марта",
        chapters=[ChapterDraft(scene_id="scene_1", text="Первая глава.")],
    )
    with pytest.raises(ValueError, match="exactly the planned scenes"):
        render_manuscript_proof(
            title="Сказка", dedication="", graph=graph, manuscript=manuscript,
        )


def test_user_text_is_xml_escaped():
    graph = build_graph(["Начало"])
    manuscript = StoryManuscript(
        hero_name="Марта",
        chapters=[ChapterDraft(scene_id="scene_1", text="Марта и <дракон> & друзья.")],
    )
    assert render_manuscript_proof(
        title="История <Марты>", dedication="Ты & я",
        graph=graph, manuscript=manuscript,
    ).startswith(b"%PDF-")
