"""Digital typography: preserve paragraphs, approved prose and long chapters."""
from io import BytesIO

from PIL import Image as PILImage
from pypdf import PdfReader

from app.little_legend.illustrated_pdf import _book_paragraphs, render_illustrated_proof
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def test_paragraphs_preserve_text_and_support_windows_line_endings() -> None:
    source = "Первый абзац.\r\n\r\nВторой абзац.\rТретий абзац."
    assert _book_paragraphs(source) == [
        "Первый абзац.", "Второй абзац.", "Третий абзац.",
    ]


def test_long_digital_chapter_flows_across_pages_without_losing_text() -> None:
    graph = build_graph(["Длинное путешествие"])
    story = " ".join(f"СекретноеСлово{number}." for number in range(200))
    manuscript = StoryManuscript(
        hero_name="Марта", parent_approved=True,
        chapters=[ChapterDraft(scene_id="scene_1", text=story, approved=True)],
    )
    picture = PILImage.new("RGB", (600, 600), "white")
    image_bytes = BytesIO()
    picture.save(image_bytes, format="PNG")
    pdf = render_illustrated_proof(
        title="Путешествие Марты", dedication="Для тебя",
        graph=graph, manuscript=manuscript,
        illustrations={"scene_1": image_bytes.getvalue()},
        approved_scene_ids={"scene_1"}, edition="digital", palette="forest",
    )
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) >= 4
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "СекретноеСлово0." in text
    assert "СекретноеСлово199." in text
    assert "РЕДАКЦИОННЫЙ МАКЕТ" not in text
