"""Verify that the customer's five goals drive both the bot and the image plan."""
import json
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.bot.handlers import wallpaper
from app.bot.states.wallpaper import WallpaperStates
from app.config import Settings
from app.services.gift_pricing import checkout_price_uah, image_cost_usd
from app.services.goal_story import GoalScenePlanner
from app.services.replicate_vision_board import ImageSafetyError

GOALS = ["Здоровье", "Путешествие", "Свой дом", "Успешный бизнес", "Любовь"]


class FakeState:
    def __init__(self, **data):
        self.data = data
        self.state = None

    async def get_data(self):
        return self.data

    async def get_state(self):
        return self.state.state if self.state is not None else None

    async def update_data(self, **values):
        self.data.update(values)

    async def set_state(self, value):
        self.state = value

    async def clear(self):
        self.data.clear()
        self.state = None


def make_photo(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (440, 540), "#bd9174").save(path)


def fake_message(user_id=42):
    notice = SimpleNamespace(delete=AsyncMock())
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id),
        answer=AsyncMock(return_value=notice), answer_photo=AsyncMock(),
        answer_document=AsyncMock())


@pytest.mark.asyncio
async def test_optional_style_selection_updates_render_job(tmp_path):
    state = FakeState(lang="ru", style="dark", render_job={"id": "old"})
    await state.set_state(WallpaperStates.waiting_for_goals)
    callback = SimpleNamespace(data="gift_style:color", answer=AsyncMock(),
                               from_user=SimpleNamespace(id=42),
                               message=SimpleNamespace(edit_reply_markup=AsyncMock()))
    await wallpaper.select_gift_style(callback, state)
    assert state.data["style"] == "color"
    assert state.data["render_job"] is None
    assert "цветную" in callback.answer.await_args.args[0]
    keyboard = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[1][2].text.startswith("✓ ")


def test_gift_image_model_has_its_own_quality_settings():
    settings = Settings(_env_file=None)
    assert settings.wallpaper_image_model == "gpt-image-2.5-sunburst"
    assert settings.wallpaper_image_quality == "xhigh"


@pytest.mark.asyncio
async def test_planner_matches_unordered_photos_to_customer_goals(tmp_path):
    photos = [tmp_path / f"{i}.jpg" for i in range(5)]
    for p in photos:
        make_photo(p)

    class Completions:
        request = None

        async def create(self, **kwargs):
            self.request = kwargs["messages"][-1]["content"]
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
                "assignments": [4, 1, 3, 2, 0],
                "scenes": [f"person in scene {n}" for n in range(5)],
            })))], usage=SimpleNamespace(prompt_tokens=2150, completion_tokens=180))

    completions = Completions()
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    plan = await GoalScenePlanner(Settings(_env_file=None), client=fake_client).plan(
        photos=photos, goals=GOALS, lang="ru")
    assert list(plan.assignments) == [4, 1, 3, 2, 0]
    assert json.loads(completions.request[0]["text"])["five_customer_goals_in_order"] == GOALS
    assert sum(part["type"] == "image_url" for part in completions.request) == 5
    assert plan.ai_cost_usd == Decimal("0.0004305")


@pytest.mark.asyncio
async def test_planner_rejects_invented_pairing_and_missing_goals(tmp_path):
    photos = [tmp_path / f"{i}.jpg" for i in range(5)]
    for p in photos:
        make_photo(p)

    class Completions:
        async def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
                "assignments": [0, 0, 1, 2, 3], "scenes": ["scene"] * 5,
            })))], usage=SimpleNamespace(prompt_tokens=200, completion_tokens=100))

    planner = GoalScenePlanner(Settings(_env_file=None), client=SimpleNamespace(
        chat=SimpleNamespace(completions=Completions())))
    with pytest.raises(ValueError):
        await planner.plan(photos=photos, goals=GOALS[:4])
    with pytest.raises(ValueError, match="pairing"):
        await planner.plan(photos=photos, goals=GOALS)
    with pytest.raises(ValueError):
        wallpaper.parse_five_goals("One\nTwo\nThree\nFour")
    assert wallpaper.parse_five_goals("\n".join(f"{i}. {goal}" for i, goal in enumerate(GOALS, 1))) == GOALS


def test_goals_can_be_full_sentences_without_artificial_caption_limit():
    goals = [
        "Хочу провести лето у моря вместе с семьёй и каждое утро встречать рассвет на берегу",
        "Мечтаю построить уютный дом с садом и большой верандой, где мы будем собираться вместе",
        "Открыть своё дело, которое приносит пользу людям и позволяет чаще быть рядом с близкими",
        "Больше путешествовать, узнавать новые места и сохранять тёплые воспоминания о каждом дне",
        "Заботиться друг о друге и проводить больше времени вместе, даже когда жизнь становится насыщенной",
    ]
    assert all(len(goal) > 42 for goal in goals)
    assert wallpaper.parse_five_goals("\n".join(goals)) == goals


@pytest.mark.asyncio
async def test_five_photo_album_waits_for_required_goals(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, storage_root=tmp_path)
    stream = BytesIO()
    Image.new("RGB", (440, 540), "#b29173").save(stream, "JPEG")
    jpeg = stream.getvalue()

    class Bot:
        async def get_file(self, file_id):
            return file_id

        async def download(self, file_id, destination):
            destination.write(jpeg)

    state = FakeState(lang="ru")
    generated = []

    async def fake_generate(message, state, settings, session_factory):
        generated.append((state.data["goals"], [p.name for p in wallpaper.upload_paths(settings, 42)]))

    monkeypatch.setattr(wallpaper, "generate_wallpapers", fake_generate)
    for message_id in (103, 105, 101, 104, 102):
        photo = SimpleNamespace(file_id=str(message_id), file_size=len(jpeg))
        message = SimpleNamespace(message_id=message_id, photo=[photo], document=None,
            caption=None, from_user=SimpleNamespace(id=42), bot=Bot(), answer=AsyncMock())
        await wallpaper.collect_five_photos(message, state, settings, None)
    assert state.state == WallpaperStates.waiting_for_goals
    assert generated == []
    await wallpaper.collect_goals(SimpleNamespace(text="\n".join(GOALS), answer=AsyncMock()),
                                  state, settings, None)
    assert generated == [(GOALS, [f"photo_{n}.jpg" for n in range(101, 106)])]


@pytest.mark.asyncio
async def test_one_photo_also_requires_goals_and_supports_caption(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, storage_root=tmp_path)
    stream = BytesIO()
    Image.new("RGB", (440, 540), "#bd9174").save(stream, "JPEG")

    class Bot:
        async def get_file(self, file_id):
            return file_id

        async def download(self, file_id, destination):
            destination.write(stream.getvalue())

    generated = []

    async def fake_generate(message, state, settings, session_factory):
        generated.append(state.data["goals"])

    monkeypatch.setattr(wallpaper, "generate_wallpapers", fake_generate)
    state = FakeState(lang="ru")
    for caption in (None, "\n".join(GOALS)):
        message = SimpleNamespace(caption=caption, photo=[SimpleNamespace(file_id="p", file_size=100)],
            document=None, from_user=SimpleNamespace(id=42), bot=Bot(), answer=AsyncMock())
        await wallpaper.collect_photo(message, state, settings, None)
        if caption is None:
            assert state.state == WallpaperStates.waiting_for_goals and generated == []
    assert generated == [GOALS]


@pytest.mark.asyncio
async def test_generates_five_scenes_and_delivers_exact_customer_goals(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, storage_root=tmp_path, free_generation_telegram_ids=(42,))
    folder = settings.uploads_dir / "wallpapers" / "42"
    for n in range(101, 106):
        make_photo(folder / f"photo_{n}.jpg")

    class Planner:
        def __init__(self, settings):
            pass

        async def plan(self, *, photos, goals, lang):
            assert list(goals) == GOALS and [p.name for p in photos] == [f"photo_{n}.jpg" for n in range(101, 106)]
            return SimpleNamespace(assignments=(4, 1, 3, 2, 0),
                scenes=("sea", "sun", "house", "office", "garden"), ai_cost_usd=Decimal("0.02"))

    delivered = []

    class Renderer:
        def __init__(self, *, output_dir, model, quality):
            self.output_dir = output_dir
            self.total_cost_usd = Decimal("0.40")
            assert model == "gpt-image-2.5-sunburst" and quality == "xhigh"

        async def generate_goal_story(self, **kwargs):
            delivered.append(kwargs)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            files = {}
            for key in ("mobile", "desktop"):
                file = self.output_dir / f"{key}.png"
                Image.new("RGB", (540, 960), "#bd9174").save(file)
                files[key] = file
            return files

    monkeypatch.setattr(wallpaper, "GoalScenePlanner", Planner)
    monkeypatch.setattr(wallpaper, "ReplicateVisionBoardRenderer", Renderer)
    monkeypatch.setattr(wallpaper, "PaymentService", lambda _settings: SimpleNamespace(portmone_ready=False))
    message = fake_message()
    await wallpaper.generate_wallpapers(message, FakeState(lang="ru", goals=GOALS), settings, None)
    assert len(delivered) == 1
    assert delivered[0]["goals"] == GOALS and delivered[0]["assignments"] == [4, 1, 3, 2, 0]
    assert delivered[0]["style"] == "dark"
    assert message.answer_photo.await_count == 2 and message.answer_document.await_count == 2
    assert not any(folder.iterdir())


@pytest.mark.asyncio
async def test_payment_uses_actual_five_scene_usage_plus_five_percent(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, storage_root=tmp_path, usd_exchange_rate=40,
                        gift_price_stars=7)
    make_photo(settings.uploads_dir / "wallpapers" / "42" / "portrait.jpg")

    class Planner:
        def __init__(self, settings):
            pass

        async def plan(self, **kwargs):
            return SimpleNamespace(assignments=(0,)*5, scenes=("a",)*5, ai_cost_usd=Decimal("0.01"))

    class Renderer:
        total_cost_usd = Decimal("0.40")

        def __init__(self, *, output_dir, model, quality):
            self.output_dir = output_dir

        async def generate_goal_story(self, **kwargs):
            self.output_dir.mkdir(parents=True, exist_ok=True)
            files = {}
            for key in ("mobile", "desktop"):
                file = self.output_dir / f"{key}.png"
                Image.new("RGB", (540, 960), "#bd9174").save(file)
                files[key] = file
            return files

    amounts = []

    class Repo:
        def __init__(self, session):
            pass

        async def create(self, **kwargs):
            amounts.append(kwargs["amount"])
            assert kwargs["stars_amount"] == 7
            return SimpleNamespace(id=7, stars_amount=7)

    class SessionFactory:
        def __call__(self):
            return self
        async def __aenter__(self):
            return object()
        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(wallpaper, "GoalScenePlanner", Planner)
    monkeypatch.setattr(wallpaper, "ReplicateVisionBoardRenderer", Renderer)
    monkeypatch.setattr(wallpaper, "WallpaperOrderRepository", Repo)
    message = fake_message()
    message.bot = SimpleNamespace(create_invoice_link=AsyncMock(return_value="https://t.me/invoice"))
    await wallpaper.generate_wallpapers(message, FakeState(lang="ru", goals=GOALS), settings, SessionFactory())
    assert amounts == [Decimal("17.22")]
    assert message.bot.create_invoice_link.await_args.kwargs["currency"] == "XTR"
    usage = SimpleNamespace(input_tokens_details=SimpleNamespace(text_tokens=200, image_tokens=2500),
        output_tokens_details=SimpleNamespace(image_tokens=6240, text_tokens=0), output_tokens=6240)
    assert checkout_price_uah(Decimal("0.01") + image_cost_usd(usage, "gpt-image-1.5"), 40) > 0


@pytest.mark.asyncio
async def test_safety_error_explains_retry_and_reuses_scene_plan(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, storage_root=tmp_path, admin_telegram_ids=(42,))
    make_photo(settings.uploads_dir / "wallpapers" / "42" / "portrait.jpg")
    plans = []
    render_dirs = []

    class Planner:
        def __init__(self, settings):
            pass

        async def plan(self, **kwargs):
            plans.append(kwargs)
            return SimpleNamespace(assignments=(0,)*5, scenes=("safe day",)*5,
                                   ai_cost_usd=Decimal("0.01"))

    class Renderer:
        total_cost_usd = Decimal("0.4")

        def __init__(self, *, output_dir, model, quality):
            self.output_dir = output_dir
            render_dirs.append(output_dir)

        async def generate_goal_story(self, **options):
            if len(render_dirs) == 1:
                raise ImageSafetyError(2, "output")
            self.output_dir.mkdir(parents=True, exist_ok=True)
            files = {}
            for name in ("mobile", "desktop"):
                path = self.output_dir / f"{name}.png"
                Image.new("RGB", (540, 960), "#bd9174").save(path)
                files[name] = path
            return files

    monkeypatch.setattr(wallpaper, "GoalScenePlanner", Planner)
    monkeypatch.setattr(wallpaper, "ReplicateVisionBoardRenderer", Renderer)
    monkeypatch.setattr(wallpaper, "PaymentService", lambda _settings: SimpleNamespace(portmone_ready=False))
    state = FakeState(lang="ru", goals=GOALS)
    message = fake_message()
    await wallpaper.generate_wallpapers(message, state, settings, None)
    assert state.state == WallpaperStates.waiting_for_goals
    assert "Готовые сцены сохранены" in message.answer.await_args.args[0]
    assert len(plans) == 1
    assert len(render_dirs) == 1
    await wallpaper.collect_goals(SimpleNamespace(text="\n".join(GOALS),
                                   from_user=message.from_user, answer=message.answer,
                                   answer_photo=message.answer_photo,
                                   answer_document=message.answer_document), state, settings, None)
    assert len(plans) == 1
    assert render_dirs == [render_dirs[0], render_dirs[0]]
    assert message.answer_document.await_count == 2


@pytest.mark.asyncio
async def test_input_block_keeps_goals_and_rejects_identical_retry(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, storage_root=tmp_path, free_generation_telegram_ids=(42,))
    photo = settings.uploads_dir / "wallpapers" / "42" / "portrait.jpg"
    make_photo(photo)
    count = 0

    class Planner:
        def __init__(self, settings):
            pass

        async def plan(self, **kwargs):
            return SimpleNamespace(assignments=(0,) * 5, scenes=("safe scene",) * 5,
                                   ai_cost_usd=Decimal("0.01"))

    class Renderer:
        def __init__(self, **kwargs):
            pass

        async def generate_goal_story(self, **kwargs):
            nonlocal count
            count += 1
            raise ImageSafetyError(6, "input", categories=("sexual",), request_id="req_example")

    monkeypatch.setattr(wallpaper, "GoalScenePlanner", Planner)
    monkeypatch.setattr(wallpaper, "ReplicateVisionBoardRenderer", Renderer)
    monkeypatch.setattr(wallpaper, "PaymentService", lambda _settings: SimpleNamespace(portmone_ready=False))
    state = FakeState(lang="ru", goals=GOALS, style="dark")
    message = fake_message()
    await wallpaper.generate_wallpapers(message, state, settings, None)
    assert state.state == WallpaperStates.waiting_for_goals
    assert state.data["goals"] == GOALS and state.data["blocked_input"] is True
    assert photo.exists()
    assert count == 1
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "gift_safety_one_photo"
    assert "сохранены" in message.answer.await_args.args[0]

    await wallpaper.collect_goals(SimpleNamespace(text="\n".join(GOALS), from_user=message.from_user,
                                  answer=message.answer), state, settings, None)
    assert count == 1
    assert state.state == WallpaperStates.waiting_for_goals


@pytest.mark.asyncio
async def test_input_block_can_request_one_new_photo_without_retyping_goals(tmp_path):
    settings = Settings(_env_file=None, storage_root=tmp_path)
    folder = settings.uploads_dir / "wallpapers" / "42"
    for n in range(5):
        make_photo(folder / f"photo_{n}.jpg")
    state = FakeState(lang="ru", goals=GOALS, style="light", blocked_input=True,
                      render_job={"id": "old"})
    callback = SimpleNamespace(data="gift_safety_one_photo", from_user=SimpleNamespace(id=42),
                               message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())
    await wallpaper.recover_blocked_gift(callback, state, settings)
    assert state.state == WallpaperStates.waiting_for_photo
    assert state.data["goals"] == GOALS and state.data["style"] == "light"
    assert state.data["render_job"] is None and state.data["blocked_input"] is False
    assert not wallpaper.upload_paths(settings, 42)
    assert "другое фото" in callback.message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_resume_keeps_saved_uploads_after_memory_state_was_lost(tmp_path):
    settings = Settings(_env_file=None, storage_root=tmp_path)
    folder = settings.uploads_dir / "wallpapers" / "42"
    for n in range(5):
        make_photo(folder / f"photo_{n}.jpg")
    state = FakeState()
    message = SimpleNamespace(from_user=SimpleNamespace(id=42, language_code="ru"),
                              answer=AsyncMock())
    await wallpaper.resume_saved_photos(message, state, settings)
    assert state.state == WallpaperStates.waiting_for_goals
    assert state.data["lang"] == "ru"
    assert len(wallpaper.upload_paths(settings, 42)) == 5
    assert "5 фото сохранены" in message.answer.await_args.args[0]
