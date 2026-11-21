"""Premium book PDF checks use generated test images, never customer photos."""
from io import BytesIO

import pytest
from PIL import Image
from pypdf import PdfReader

from app.little_legend.premium_pdf import render_premium_book
from app.little_legend.premium_visual_contract import BookGenre, build_visual_plan
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def _image(color):
    buffer = BytesIO()
    Image.new("RGB", (720, 960), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _inputs():
    graph = build_graph(["First scene", "Second scene"])
    manuscript = StoryManuscript(
        hero_name="Тестовый герой", parent_approved=True,
        chapters=[
            ChapterDraft(
                scene_id=node.id,
                text=("Длинная история с приключениями. " * 55),
                approved=True,
            )
            for node in graph.nodes
        ],
    )
    plan = build_visual_plan(
        genre=BookGenre.EPIC_FANTASY,
        reference_ids=["private-ref-1", "private-ref-2", "private-ref-3"],
        chapter_moments=[
            ("Finding a map", "Crossing the bridge"),
            ("Meeting a friend", "Returning home"),
        ],
    )
    pictures = {
        slot.moment_id: _image((30 + i * 30, 80, 110))
        for i, slot in enumerate(plan.illustrations)
    }
    return dict(
        title="История о герое", dedication="Для тебя",
        graph=graph, manuscript=manuscript, plan=plan,
        cover=_image((80, 50, 120)), illustrations=pictures,
        approved_moment_ids=set(pictures), cover_approved=True,
    )


def test_premium_pdf_has_distinct_cover_and_two_large_images_per_chapter():
    params = _inputs()
    pdf = render_premium_book(**params)
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) >= 10
    image_pages = [page for page in reader.pages if page.images]
    assert len(image_pages) == 5
    full_text = " ".join(page.extract_text() or "" for page in reader.pages)
    assert "История о герое" in full_text
    assert "Длинная история" in full_text


def test_missing_second_image_is_rejected():
    params = _inputs()
    params["illustrations"].pop("chapter-01-moment-2")
    with pytest.raises(PermissionError):
        render_premium_book(**params)


def test_cover_must_be_approved():
    params = _inputs()
    params["cover_approved"] = False
    with pytest.raises(PermissionError):
        render_premium_book(**params)


def test_manuscript_must_be_approved():
    params = _inputs()
    params["manuscript"].parent_approved = False
    with pytest.raises(PermissionError):
        render_premium_book(**params)


def test_invalid_image_is_rejected():
    params = _inputs()
    params["illustrations"]["chapter-01-moment-1"] = b"not-an-image"
    with pytest.raises(ValueError):
        render_premium_book(**params)
