"""A blocked image edit must not discard the finished, paid phone artwork."""

import base64
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from openai import BadRequestError
from PIL import Image

from app.services import replicate_vision_board as board


def blocked_output() -> BadRequestError:
    response = httpx.Response(400, request=httpx.Request("POST", "https://api.openai.com/v1/images/edits"))
    return BadRequestError("Image check blocked the output", response=response, body={
        "code": "moderation_blocked",
        "moderation_details": {"moderation_stage": "output", "categories": ["sexual"]},
    })


class FakeImages:
    def __init__(self, blocked_calls=()):
        self.calls = []
        self.blocked_calls = set(blocked_calls)
        picture = BytesIO()
        Image.new("RGB", (700, 700), "#80654f").save(picture, "PNG")
        self.image = base64.b64encode(picture.getvalue()).decode()

    async def edit(self, **kwargs):
        self.calls.append(kwargs["prompt"])
        if len(self.calls) in self.blocked_calls:
            raise blocked_output()
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=self.image)],
            usage=SimpleNamespace(
                input_tokens_details=SimpleNamespace(text_tokens=100, image_tokens=300),
                output_tokens_details=SimpleNamespace(image_tokens=1000, text_tokens=0),
                output_tokens=1000,
            ),
        )


@pytest.mark.asyncio
async def test_output_rejection_retries_once_with_neutral_scene(tmp_path, monkeypatch):
    monkeypatch.setattr(board, "SIZES", {"9:16": (540, 960), "16:9": (960, 540)})
    photo = tmp_path / "person.jpg"
    Image.new("RGB", (440, 540), "#876040").save(photo)
    images = FakeImages(blocked_calls=(1,))
    renderer = board.ReplicateVisionBoardRenderer(
        output_dir=tmp_path / "render", client=SimpleNamespace(images=images))
    formats = await renderer.generate_goal_story(
        user_id=12, photo_paths=[photo], goals=["Здоровье", "Море", "Дом", "Бизнес", "Любовь"],
        assignments=[0]*5, scenes=["gentle real-life scene"]*5,
    )
    assert len(images.calls) == 4  # one refused draft, neutral retry, polish, desktop
    assert "family greeting-card" in images.calls[1]
    assert all(path.is_file() for path in formats.values())
    assert len(list((tmp_path / "render").glob("editorial_v5_dark_*.png"))) == 3
    first_cost = renderer.total_cost_usd
    fresh = board.ReplicateVisionBoardRenderer(
        output_dir=tmp_path / "render", client=SimpleNamespace(images=images))
    await fresh.generate_goal_story(user_id=12, photo_paths=[photo],
        goals=["Здоровье", "Море", "Дом", "Бизнес", "Любовь"],
        assignments=[0]*5, scenes=["gentle real-life scene"]*5)
    assert len(images.calls) == 4
    assert fresh.total_cost_usd == first_cost


@pytest.mark.asyncio
async def test_two_rejections_leave_no_stale_artwork(tmp_path, monkeypatch):
    monkeypatch.setattr(board, "SIZES", {"9:16": (540, 960), "16:9": (960, 540)})
    photo = tmp_path / "person.jpg"
    Image.new("RGB", (440, 540), "#876040").save(photo)
    images = FakeImages(blocked_calls=(1, 2))
    render_dir = tmp_path / "render"
    renderer = board.ReplicateVisionBoardRenderer(
        output_dir=render_dir, client=SimpleNamespace(images=images))
    options = dict(user_id=12, photo_paths=[photo], goals=["Здоровье", "Море", "Дом", "Бизнес", "Любовь"],
                   assignments=[0]*5, scenes=["gentle real-life scene"]*5)
    with pytest.raises(board.ImageSafetyError) as raised:
        await renderer.generate_goal_story(**options)
    assert raised.value.scene_number == 6 and raised.value.stage == "output"
    assert not (render_dir / "editorial_v5_dark_mobile_draft.png").exists()

    fresh = board.ReplicateVisionBoardRenderer(
        output_dir=render_dir, client=SimpleNamespace(images=images))
    await fresh.generate_goal_story(**options)
    assert len(images.calls) == 5  # two refusals followed by three completed stages
    assert fresh.total_cost_usd > 0


@pytest.mark.asyncio
async def test_desktop_failure_resumes_without_paying_for_mobile_again(tmp_path, monkeypatch):
    monkeypatch.setattr(board, "SIZES", {"9:16": (540, 960), "16:9": (960, 540)})
    photo = tmp_path / "person.jpg"
    Image.new("RGB", (440, 540), "#876040").save(photo)
    images = FakeImages(blocked_calls=(3, 4))
    render_dir = tmp_path / "render"
    options = dict(user_id=12, photo_paths=[photo],
                   goals=["Здоровье", "Море", "Дом", "Бизнес", "Любовь"],
                   assignments=[0]*5, scenes=["gentle real-life scene"]*5)
    renderer = board.ReplicateVisionBoardRenderer(
        output_dir=render_dir, client=SimpleNamespace(images=images))
    with pytest.raises(board.ImageSafetyError) as raised:
        await renderer.generate_goal_story(**options)
    assert raised.value.scene_number == 7
    assert (render_dir / "editorial_v5_dark_mobile_draft.png").is_file()
    assert (render_dir / "editorial_v5_dark_mobile.png").is_file()
    assert (render_dir / "editorial_v5_dark_mobile.json").is_file()
    assert not (render_dir / "editorial_v5_dark_desktop.png").exists()
    fresh = board.ReplicateVisionBoardRenderer(
        output_dir=render_dir, client=SimpleNamespace(images=images))
    result = await fresh.generate_goal_story(**options)
    assert all(path.is_file() for path in result.values())
    assert len(images.calls) == 5
    assert fresh.total_cost_usd > renderer.total_cost_usd


@pytest.mark.asyncio
async def test_polish_failure_reuses_the_paid_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(board, "SIZES", {"9:16": (540, 960), "16:9": (960, 540)})
    photo = tmp_path / "person.jpg"
    Image.new("RGB", (440, 540), "#876040").save(photo)
    images = FakeImages(blocked_calls=(2, 3))
    render_dir = tmp_path / "render"
    options = dict(user_id=12, photo_paths=[photo], goals=["Здоровье", "Море", "Дом", "Бизнес", "Любовь"],
                   assignments=[0]*5, scenes=["gentle real-life scene"]*5)
    renderer = board.ReplicateVisionBoardRenderer(
        output_dir=render_dir, client=SimpleNamespace(images=images))
    with pytest.raises(board.ImageSafetyError):
        await renderer.generate_goal_story(**options)
    assert (render_dir / "editorial_v5_dark_mobile_draft.png").is_file()
    assert not (render_dir / "editorial_v5_dark_mobile.png").exists()
    assert renderer.total_cost_usd > 0

    resumed = board.ReplicateVisionBoardRenderer(
        output_dir=render_dir, client=SimpleNamespace(images=images))
    await resumed.generate_goal_story(**options)
    assert len(images.calls) == 5  # draft + two refused polishes + polish + desktop
    assert resumed.total_cost_usd > renderer.total_cost_usd


def test_other_bad_requests_are_not_treated_as_safety_refusals():
    response = httpx.Response(400, request=httpx.Request("POST", "https://api.openai.com/v1/images/edits"))
    error = BadRequestError("invalid size", response=response, body={"code": "invalid_request_error"})
    assert board.moderation_stage(error) is None
