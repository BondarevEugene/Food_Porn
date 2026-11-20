"""Regression tests for premium A5 composition and safe cover typography."""

from io import BytesIO

import pytest
from PIL import Image as PILImage
from pypdf import PdfReader
from reportlab.lib.pagesizes import A5

from app.little_legend.illustrated_pdf import (
    EDITION_PALETTES,
    render_illustrated_proof,
)
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def _book(*, palette: str, title: str, edition: str) -> bytes:
    graph = build_graph(["Волшебный сад"])
    manuscript = StoryManuscript(
        hero_name="Марта",
        parent_approved=True,
        chapters=[
            ChapterDraft(
                scene_id="scene_1",
                text="Марта нашла волшебный сад. " * 15,
                approved=True,
            ),
        ],
    )
    image = BytesIO()
    PILImage.new("RGB", (900, 900), "#e0c7ef").save(image, format="PNG")
    return render_illustrated_proof(
        title=title,
        dedication="С любовью",
        graph=graph,
        manuscript=manuscript,
        illustrations={"scene_1": image.getvalue()},
        approved_scene_ids={"scene_1"},
        palette=palette,
        edition=edition,
    )


@pytest.mark.parametrize("palette", sorted(EDITION_PALETTES))
def test_all_fifteen_cover_palettes_render_valid_a5(palette):
    reader = PdfReader(BytesIO(_book(
        palette=palette, title="Приключения Марты", edition="digital",
    )))
    assert len(reader.pages) >= 3
    assert len(reader.pages[0].images) >= 1
    assert all(
        abs(float(page.mediabox.width) - A5[0]) < 1
        and abs(float(page.mediabox.height) - A5[1]) < 1
        for page in reader.pages
    )
    text = " ".join(page.extract_text() or "" for page in reader.pages)
    assert "Марта нашла волшебный сад" in text


@pytest.mark.parametrize("edition", ["digital", "editorial_proof"])
def test_long_cover_title_and_chapter_art_survive_layout(edition):
    title = "Марта и невероятно длинное путешествие по волшебным мирам сказочного королевства"
    reader = PdfReader(BytesIO(_book(
        palette="midnight", title=title, edition=edition,
    )))
    text = " ".join(page.extract_text() or "" for page in reader.pages)
    assert "Марта" in text
    assert "волшебный сад" in text
    assert len(reader.pages[0].images) >= 1
    assert "ГЛАВА 01" in text
