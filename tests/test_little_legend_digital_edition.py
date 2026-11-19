"""Paid digital editions must never expose editorial proof notices."""
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.little_legend.illustrated_pdf import render_illustrated_proof
from tests.test_little_legend_illustrated_pdf import sample


def test_paid_digital_book_is_clean_and_keeps_approved_story():
    graph, manuscript, image = sample()
    pdf = render_illustrated_proof(
        title="Сказка Марты", dedication="С любовью",
        graph=graph, manuscript=manuscript,
        illustrations={"scene_1": image}, approved_scene_ids={"scene_1"},
        edition="digital",
    )
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "EDITORIAL PROOF" not in text
    assert "РЕДАКЦИОННЫЙ МАКЕТ" not in text
    assert "Редакторская информация" not in text
    assert "Сказка Марты" in text
    assert "Марта вошла в сад" in text
    assert len(reader.pages[0].images) >= 1


def test_unsupported_edition_fails_closed():
    graph, manuscript, image = sample()
    with pytest.raises(ValueError, match="edition"):
        render_illustrated_proof(
            title="Сказка", dedication="", graph=graph,
            manuscript=manuscript, illustrations={"scene_1": image},
            approved_scene_ids={"scene_1"}, edition="print_ready",
        )
