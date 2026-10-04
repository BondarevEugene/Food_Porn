"""Check the five uploaded photos really reach the image edit API in order."""
import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.bot.handlers.wallpaper import make_preview
from app.services import replicate_vision_board


class FakeImages:
    def __init__(self):
        self.calls = []

    async def edit(self, **kwargs):
        first_pixel = []
        for file in kwargs["image"]:
            with Image.open(file) as photo:
                first_pixel.append(photo.getpixel((0, 0))[0])
        self.calls.append((first_pixel, kwargs))
        picture = Image.new("RGB", (1024, 1536), (62, 45, 34))
        output = BytesIO()
        picture.save(output, "PNG")
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(output.getvalue()).decode())],
            usage=SimpleNamespace(
                input_tokens_details=SimpleNamespace(text_tokens=80, image_tokens=1000),
                output_tokens=6240, output_tokens_details=None,
            ),
        )


@pytest.mark.asyncio
async def test_five_photos_and_runtime_goals_reach_image_edit(tmp_path, monkeypatch):
    monkeypatch.setattr(replicate_vision_board, "SIZES", {
        "9:16": (540, 960), "16:9": (960, 540), "reference": (540, 960),
    })
    photos: list[Path] = []
    for index in range(5):
        photo = tmp_path / f"{index}.jpg"
        Image.new("RGB", (440, 540), (30 + index * 37, 45, 85)).save(photo)
        photos.append(photo)
    goals = ["Семья", "Море", "Дом", "Бизнес", "Свобода"]
    fake = FakeImages()
    renderer = replicate_vision_board.ReplicateVisionBoardRenderer(output_dir=tmp_path, client=SimpleNamespace(images=fake))
    mobile = await renderer.generate_from_telegram(user_id=12, goals=goals, photo_paths=photos)
    desktop = await renderer.generate_wallpaper(
        12, goals, str(photos[0]), aspect_ratio="16:9",
        inspiration_images=[str(photo) for photo in photos[1:]],
    )
    assert Image.open(mobile).size == (540, 960)
    assert Image.open(desktop).size == (960, 540)
    assert len(fake.calls) == 2
    assert fake.calls[0][0] == sorted(fake.calls[0][0])
    assert len(set(fake.calls[0][0])) == 5
    assert all(phrase in fake.calls[0][1]["prompt"] for phrase in goals[:4])
    assert fake.calls[0][1]["size"] == "1024x1536"
    assert fake.calls[1][1]["size"] == "1536x1024"
    assert fake.calls[0][1]["quality"] == "medium"
    assert renderer.total_cost_usd > 0
    gift = await renderer.generate_gift(
        user_id=12, portrait=photos[0], scenes=["sunset", "garden", "coast", "dinner"],
        captions=goals[:4], title=goals[4],
    )
    assert Image.open(gift).size == (540, 960)
    assert len(fake.calls[-1][0]) == 1
    assert "sunset" in fake.calls[-1][1]["prompt"]
    with pytest.raises(ValueError):
        await renderer.generate_from_telegram(user_id=12, goals=goals, photo_paths=photos[:4])

    auto = await renderer.generate_five_photo_gift(
        user_id=12, photo_paths=photos, scenes=["coast", "garden", "city", "terrace"],
        captions=["Море", "Сад", "Город", "Вечер"], title="Для тебя",
    )
    assert Image.open(auto).size == (540, 960)
    assert len(fake.calls[-1][0]) == 5
    assert "Photo 2, surrounding scene 1: coast" in fake.calls[-1][1]["prompt"]


@pytest.mark.asyncio
async def test_customer_goals_use_original_photos_for_both_artworks(tmp_path, monkeypatch):
    monkeypatch.setattr(replicate_vision_board, "SIZES", {"9:16": (540, 960), "16:9": (960, 540)})
    photos = []
    for n in range(5):
        file = tmp_path / f"source_{n}.jpg"
        Image.new("RGB", (440, 540), (50+n*27, 90, 110)).save(file)
        photos.append(file)
    goal_words = ["Здоровье", "Путешествие", "Дом", "Бизнес", "Любовь"]
    fake = FakeImages()
    renderer = replicate_vision_board.ReplicateVisionBoardRenderer(
        output_dir=tmp_path / "out", model="gpt-image-2.5-sunburst", quality="xhigh",
        client=SimpleNamespace(images=fake))
    labels = []
    original_labels = renderer._render_goal_labels
    def record_labels(image, goals, ratio):
        labels.append((list(goals), ratio))
        return original_labels(image, goals, ratio)
    monkeypatch.setattr(renderer, "_render_goal_labels", record_labels)
    outputs = await renderer.generate_goal_story(
        user_id=12, photo_paths=photos, goals=goal_words,
        assignments=[3, 1, 4, 2, 0],
        scenes=["soft studio", "warm coast", "tall windows", "calm desk", "flowers"],
        style="light",
    )
    assert Image.open(outputs["mobile"]).size == (540, 960)
    assert Image.open(outputs["desktop"]).size == (960, 540)
    assert labels == [(goal_words, "9:16"), (goal_words, "16:9"),
                      (goal_words, "9:16"), (goal_words, "16:9")]
    assert len(fake.calls) == 3
    assert [len(call[0]) for call in fake.calls] == [5, 6, 6]
    assert fake.calls[0][0] == sorted(fake.calls[0][0])
    assert [call[1]["size"] for call in fake.calls] == ["1088x1920", "1088x1920", "1920x1088"]
    assert all(call[1]["quality"] == "xhigh" for call in fake.calls)
    assert all(call[1]["model"] == "gpt-image-2.5-sunburst" for call in fake.calls)
    assert all(word in fake.calls[0][1]["prompt"] for word in goal_words)
    assert "source photo 4" in fake.calls[0][1]["prompt"]
    assert "luminous editorial" in fake.calls[0][1]["prompt"]
    assert "NO tiles" in fake.calls[0][1]["prompt"]
    assert "ORIGINAL identity references" in fake.calls[1][1]["prompt"]
    assert "Input photos 2 through 5" in fake.calls[2][1]["prompt"]
    assert len(list((tmp_path / "out").glob("editorial_v5_light_*.png"))) == 3
    assert "No moment is a large center portrait" in fake.calls[0][1]["prompt"]
    for saved in outputs.values():
        with Image.open(saved) as picture:
            # No original-source oval is composited over the AI artwork.
            hero = picture.getpixel((picture.width//2, picture.height//2))
            edge = picture.getpixel((0, 0))
            source_rgb = (50, 90, 110)
            hero_distance = sum(abs(a-b) for a, b in zip(hero, source_rgb, strict=True))
            edge_distance = sum(abs(a-b) for a, b in zip(edge, source_rgb, strict=True))
            assert abs(hero_distance - edge_distance) < 5
    assert renderer.total_cost_usd > 0
    fresh = replicate_vision_board.ReplicateVisionBoardRenderer(
        output_dir=tmp_path / "out", model="gpt-image-2.5-sunburst",
        client=SimpleNamespace(images=fake))
    await fresh.generate_goal_story(user_id=12, photo_paths=photos, goals=goal_words,
        assignments=[3, 1, 4, 2, 0],
        scenes=["soft studio", "warm coast", "tall windows", "calm desk", "flowers"],
        style="light")
    assert len(fake.calls) == 3
    assert fresh.total_cost_usd == renderer.total_cost_usd
    with pytest.raises(ValueError):
        await renderer.generate_goal_story(user_id=12, photo_paths=photos,
            goals=goal_words[:4], assignments=[0]*5, scenes=["x"]*5)


@pytest.mark.asyncio
async def test_seven_photos_nine_goals_reach_both_renders_and_labels(tmp_path, monkeypatch):
    monkeypatch.setattr(replicate_vision_board, "SIZES", {"9:16": (540, 960), "16:9": (960, 540)})
    photos = []
    for index in range(7):
        path = tmp_path / f"source_{index}.jpg"
        Image.new("RGB", (440, 540), (30 + index * 30, 55, 70)).save(path)
        photos.append(path)
    goals = [f"Wish number {index}" for index in range(1, 10)]
    fake = FakeImages()
    renderer = replicate_vision_board.ReplicateVisionBoardRenderer(
        output_dir=tmp_path / "nine", client=SimpleNamespace(images=fake))
    outputs = await renderer.generate_goal_story(
        user_id=12, photo_paths=photos, goals=goals,
        assignments=[0, 1, 2, 3, 4, 5, 6, 0, 1], scenes=["bright natural scene"] * 9,
    )
    assert [len(call[0]) for call in fake.calls] == [7, 8, 8]
    assert "9 wishes" in fake.calls[0][1]["prompt"]
    assert "Story moment 9" in fake.calls[0][1]["prompt"]
    assert all("Input photos 2 through 7" in fake.calls[index][1]["prompt"] for index in (0, 2))
    assert Image.open(outputs["mobile"]).size == (540, 960)
    assert Image.open(outputs["desktop"]).size == (960, 540)
    with pytest.raises(ValueError, match="pairing"):
        await renderer.generate_goal_story(user_id=12, photo_paths=photos,
            goals=goals, assignments=[0]*9, scenes=["scene"]*9)


def test_preview_preserves_full_resolution(tmp_path):
    art = tmp_path / "mobile.png"
    Image.new("RGB", (1080, 1920), "#b18d70").save(art)
    preview = make_preview(art)
    with Image.open(preview) as image:
        assert image.size == (1080, 1920)
        assert image.format == "JPEG"
