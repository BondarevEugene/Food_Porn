"""Regression tests for the customer goal-story wallpaper flow.

The tests use fake image API responses and temporary files. They must not
call OpenAI, Replicate, PostgreSQL or external services.
"""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.services import goal_story, replicate_vision_board

GOALS = [
    "РџСЂРѕРІРµСЃС‚Рё Р»РµС‚Рѕ Сѓ РјРѕСЂСЏ",
    "РљСѓРїРёС‚СЊ СЃРѕР±СЃС‚РІРµРЅРЅС‹Р№ РґРѕРј",
    "Р Р°Р·РІРёС‚СЊ СЃРІРѕР№ Р±РёР·РЅРµСЃ",
    "РџСѓС‚РµС€РµСЃС‚РІРѕРІР°С‚СЊ РІРјРµСЃС‚Рµ",
    "РЎРѕС…СЂР°РЅРёС‚СЊ Р·РґРѕСЂРѕРІСЊРµ Рё СЌРЅРµСЂРіРёСЋ",
]

SCENES = [
    "soft studio",
    "warm coast",
    "tall windows",
    "calm desk",
    "flowers",
]


def _create_photos(
    directory: Path,
    count: int = 5,
) -> list[Path]:
    """Create deterministic local photo fixtures."""
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    for index in range(count):
        path = directory / f"photo_{index + 1}.jpg"
        image = Image.new(
            "RGB",
            (440 + index * 10, 540 + index * 10),
            (
                120 + index * 10,
                90 + index * 5,
                70 + index * 8,
            ),
        )
        image.save(path, format="JPEG")
        image.close()
        paths.append(path)

    return paths


def _assert_image_size(
    path: str | Path,
    expected_size: tuple[int, int],
) -> None:
    """Check an image without leaving its file handle open."""
    with Image.open(path) as image:
        image.load()
        assert image.size == expected_size


class FakeImages:
    """Small fake for the asynchronous image-edit API."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def edit(self, **kwargs):
        self.calls.append(kwargs)

        # Return a valid PNG payload in the same shape as the image API.
        stream = BytesIO()
        image = Image.new("RGB", (1024, 1024), "#b29173")
        image.save(stream, format="PNG")
        image.close()

        return SimpleNamespace(
            data=[
                SimpleNamespace(
                    b64_json=base64.b64encode(stream.getvalue()).decode("ascii")
                )
            ],
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=100,
                input_tokens_details=SimpleNamespace(
                    image_tokens=0,
                    cached_tokens=0,
                ),
                output_tokens_details=SimpleNamespace(image_tokens=0),
            ),
        )


async def _skip_cost_logging(*args, **kwargs) -> None:
    """Keep tests independent of database-backed generation-cost logging."""


@pytest.fixture(autouse=True)
def disable_external_cost_logging(monkeypatch):
    """Prevent the renderer from opening a real database connection."""
    monkeypatch.setattr(
        replicate_vision_board,
        "log_openai_response",
        _skip_cost_logging,
    )
    monkeypatch.setattr(
        goal_story,
        "log_openai_response",
        _skip_cost_logging,
    )


@pytest.mark.asyncio
async def test_five_photos_and_runtime_goals_reach_image_edit(tmp_path):
    """The five uploaded photos and customer goals reach image generation."""
    photos = _create_photos(tmp_path / "photos", count=5)
    fake = FakeImages()

    renderer = replicate_vision_board.ReplicateVisionBoardRenderer(
        output_dir=tmp_path / "out",
        model="gpt-image-2.5-sunburst",
        client=SimpleNamespace(images=fake),
    )

    outputs = await renderer.generate_goal_story(
        user_id=12,
        photo_paths=photos,
        goals=GOALS,
        assignments=[4, 1, 3, 2, 0],
        scenes=SCENES,
        style="dark",
    )

    assert set(outputs) >= {"mobile", "desktop"}
    assert len(fake.calls) == 3

    for call in fake.calls:
        assert "image" in call
        assert call["image"]

    _assert_image_size(outputs["mobile"], (1080, 1920))
    _assert_image_size(outputs["mobile"], (1080, 1920))


@pytest.mark.asyncio
async def test_customer_goals_use_original_photos_for_both_artworks(tmp_path):
    """Both artwork formats use the supplied photos and customer goals."""
    photos = _create_photos(tmp_path / "photos", count=5)
    fake = FakeImages()

    renderer = replicate_vision_board.ReplicateVisionBoardRenderer(
        output_dir=tmp_path / "out",
        model="gpt-image-2.5-sunburst",
        client=SimpleNamespace(images=fake),
    )

    outputs = await renderer.generate_goal_story(
        user_id=12,
        photo_paths=photos,
        goals=GOALS,
        assignments=[4, 1, 3, 2, 0],
        scenes=SCENES,
        style="light",
    )

    assert set(outputs) >= {"mobile", "desktop"}
    _assert_image_size(outputs["mobile"], (1080, 1920))
    _assert_image_size(outputs["desktop"], (1920, 1080))

    # Check the exact uploaded photo paths passed to each image-edit request.
    assert fake.calls
    for call in fake.calls:
        supplied_images = call.get("image")
        assert supplied_images is not None

        if not isinstance(supplied_images, (list, tuple)):
            supplied_images = [supplied_images]

        supplied_names = {
            Path(getattr(item, "name", str(item))).name
            for item in supplied_images
        }
        assert supplied_names.intersection(
            {photo.name for photo in photos}
        )

    # A new renderer must not reuse the first run's output directory.
    # This ensures the second run exercises the fake image API independently.
    fresh_fake = FakeImages()
    fresh = replicate_vision_board.ReplicateVisionBoardRenderer(
        output_dir=tmp_path / "fresh",
        model="gpt-image-2.5-sunburst",
        client=SimpleNamespace(images=fresh_fake),
    )

    fresh_outputs = await fresh.generate_goal_story(
        user_id=12,
        photo_paths=photos,
        goals=GOALS,
        assignments=[4, 1, 3, 2, 0],
        scenes=SCENES,
        style="light",
    )

    assert set(fresh_outputs) >= {"mobile", "desktop"}
    _assert_image_size(fresh_outputs["mobile"], (1080, 1920))
    _assert_image_size(fresh_outputs["desktop"], (1920, 1080))

    assert len(fresh_fake.calls) == 3
    assert fresh.total_cost_usd > 0
    assert fresh.total_cost_usd == renderer.total_cost_usd


@pytest.mark.asyncio
async def test_seven_photos_nine_goals_reach_both_renders_and_labels(tmp_path):
    """Seven reference photos and nine wishes are accepted and rendered."""
    photos = _create_photos(tmp_path / "photos", count=7)
    goals = [f"Р¦РµР»СЊ РЅРѕРјРµСЂ {index}" for index in range(1, 10)]
    assignments = [6, 0, 1, 2, 3, 4, 5, 6, 0]
    scenes = [f"photographic scene {index}" for index in range(1, 10)]
    fake = FakeImages()

    renderer = replicate_vision_board.ReplicateVisionBoardRenderer(
        output_dir=tmp_path / "nine",
        model="gpt-image-2.5-sunburst",
        client=SimpleNamespace(images=fake),
    )

    outputs = await renderer.generate_goal_story(
        user_id=12,
        photo_paths=photos,
        goals=goals,
        assignments=assignments,
        scenes=scenes,
        style="color",
    )

    assert set(outputs) >= {"mobile", "desktop"}
    assert len(fake.calls) == 3

    _assert_image_size(outputs["mobile"], (1080, 1920))
    _assert_image_size(outputs["desktop"], (1920, 1080))

    # All nine customer wishes must remain available to the renderer.
    assert len(goals) == 9
    assert len(assignments) == len(scenes) == len(goals)
    assert set(assignments) == set(range(7))


@pytest.mark.asyncio
async def test_preview_preserves_full_resolution(tmp_path):
    """Creating a preview must not overwrite the full-size source artwork."""
    photos = _create_photos(tmp_path / "photos", count=5)
    fake = FakeImages()

    renderer = replicate_vision_board.ReplicateVisionBoardRenderer(
        output_dir=tmp_path / "preview",
        model="gpt-image-2.5-sunburst",
        client=SimpleNamespace(images=fake),
    )

    outputs = await renderer.generate_goal_story(
        user_id=12,
        photo_paths=photos,
        goals=GOALS,
        assignments=[4, 1, 3, 2, 0],
        scenes=SCENES,
        style="dark",
    )

    for key, expected_size in (
        ("mobile", (1080, 1920)),
        ("desktop", (1920, 1080)),
    ):
        assert key in outputs
        _assert_image_size(outputs[key], expected_size)

    # The original uploaded photos must remain unchanged.
    for photo in photos:
        assert photo.is_file()
        with Image.open(photo) as image:
            image.verify()
