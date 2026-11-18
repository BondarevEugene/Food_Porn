"""Story Graph and print-proof regression tests."""
import pytest
from pydantic import ValidationError
from app.little_legend.print_renderer import render_print_proof
from app.little_legend.story_graph import StoryEdge, StoryGraph, build_graph, graph_report


def test_default_graph_is_connected_and_has_three_acts():
    graph = build_graph([f"Событие {n}" for n in range(12)])
    assert len(graph.nodes) == 12
    assert len(graph.edges) == 11
    assert set(node.act for node in graph.nodes) == {1, 2, 3}
    assert graph_report(graph)["ready_for_editorial_review"] is True


def test_story_graph_rejects_broken_reference_and_disconnected_scene():
    graph = build_graph(["Первое", "Второе"])
    with pytest.raises(ValidationError):
        StoryGraph(nodes=graph.nodes, edges=[StoryEdge(source="scene_1", target="missing")])
    with pytest.raises(ValidationError):
        StoryGraph(nodes=graph.nodes, edges=[])


def test_pdf_proof_is_readable_and_cyrillic():
    graph = build_graph(["Встреча в лесу", "Открытие тайны"])
    pdf = render_print_proof(
        title="Лес, который помнил звёзды", hero="Оля",
        dedication="Для самой смелой девочки", city="Киев", graph=graph,
    )
    assert pdf.startswith(b"%PDF")
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) >= 4
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Лес, который помнил звёзды" in text
    assert "ПРОБНЫЙ МАКЕТ" in text
