"""Exercise real SDK error branches, request counts and order recovery."""

from __future__ import annotations

import asyncio
import base64
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APITimeoutError, AsyncOpenAI, BadRequestError, RateLimitError
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot.handlers import wallpaper
from app.config import Settings
from app.database.models import (
    Base,
    Customer,
    GenerationStatus,
    ItemCategory,
    Language,
    Menu,
    MenuItem,
    MenuStatus,
)
from app.miniapp import api
from app.services import openai_errors as policy
from app.services.image_generation import ImageGenerationService, QuotaExhaustedError
from app.services.recipe_generator import RecipeGeneratorService
from app.services.replicate_vision_board import ReplicateVisionBoardRenderer
from app.services.wallpaper_renderer import WallpaperRenderer
from app.workers.menu_pipeline import MenuPipeline


@pytest.fixture(autouse=True)
def clear_circuits():
    policy._circuits.clear()
    policy._rate_blocks.clear()
    yield
    policy._circuits.clear()
    policy._rate_blocks.clear()


def sdk_error(
    status=429, code="credit_balance_exhausted", error_type="insufficient_quota", headers=None
):
    response = httpx.Response(
        status,
        headers={"x-request-id": "req_test", **(headers or {})},
        request=httpx.Request("POST", "https://api.openai.com/v1/images/generations"),
    )
    body = {
        "error": {
            "code": code,
            "type": error_type,
            "message": "SECRET CUSTOMER INPUT sk-secret-example",
        }
    }
    from openai import APIStatusError

    cls = RateLimitError if status == 429 else BadRequestError if status == 400 else APIStatusError
    return cls("SECRET CUSTOMER INPUT sk-secret-example", response=response, body=body)


@pytest.mark.parametrize("code", sorted(policy.QUOTA_CODES))
async def test_all_billing_codes_block_other_products_after_one_request(code, caplog):
    request = AsyncMock(side_effect=sdk_error(code=code))
    with pytest.raises(policy.OpenAIServiceError) as caught:
        await policy.request_openai(
            request, api_key="secret-key", operation="menu_image", attempts=4
        )
    assert caught.value.problem.kind == "quota"
    assert caught.value.code == code
    other_product = AsyncMock()
    with pytest.raises(policy.OpenAIServiceError):
        await policy.request_openai(other_product, api_key="secret-key", operation="gift_plan")
    request.assert_awaited_once()
    other_product.assert_not_awaited()
    assert "SECRET CUSTOMER INPUT" not in caplog.text
    assert "sk-secret-example" not in str(caught.value)
    assert "req_test" in caplog.text


@pytest.mark.parametrize(
    ("status", "code", "kind"),
    [
        (401, "invalid_api_key", "auth"),
        (403, "permission_denied", "access"),
        (404, "model_not_found", "config"),
        (400, "invalid_request_error", "request"),
        (400, "moderation_blocked", "safety"),
        (429, "rate_limit_exceeded", "rate_limit"),
        (500, "server_error", "server"),
        (408, "request_timeout", "timeout"),
    ],
)
def test_http_error_classification(status, code, kind):
    error = sdk_error(status, code, error_type="api_error")
    assert policy.classify_openai_error(error).kind == kind


async def test_unknown_specific_code_with_insufficient_quota_type_is_still_billing():
    failure = sdk_error(code="new_billing_code")
    call = AsyncMock(side_effect=failure)
    with pytest.raises(policy.OpenAIServiceError) as raised:
        await policy.request_openai(call, api_key="test-key", operation="image", attempts=4)
    assert raised.value.problem.kind == "quota"
    assert raised.value.code == "new_billing_code"
    call.assert_awaited_once()


async def test_rate_limit_honors_retry_after_and_then_succeeds(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(policy.asyncio, "sleep", sleep)
    call = AsyncMock(
        side_effect=[
            sdk_error(
                code="rate_limit_exceeded",
                error_type="rate_limit_error",
                headers={"retry-after": "3"},
            ),
            "ready",
        ]
    )
    result = await policy.request_openai(call, api_key="test-key", operation="image", attempts=2)
    assert result == "ready"
    assert call.await_count == 2
    sleep.assert_awaited_once_with(3.0)


async def test_long_retry_after_is_not_shortened_and_manual_retries_make_no_request(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(policy.asyncio, "sleep", sleep)
    call = AsyncMock(
        side_effect=sdk_error(
            code="rate_limit_exceeded",
            error_type="rate_limit_error",
            headers={"retry-after": "120"},
        )
    )
    for _ in range(2):
        with pytest.raises(policy.OpenAIServiceError) as raised:
            await policy.request_openai(call, api_key="test-key", operation="image", attempts=4)
        assert raised.value.problem.retry_after > 119
    call.assert_awaited_once()
    sleep.assert_not_awaited()


@pytest.mark.parametrize("image_request", [True, False])
async def test_image_timeout_has_no_automatic_duplicate_but_text_retry_is_bounded(
    monkeypatch, image_request
):
    monkeypatch.setattr(policy.asyncio, "sleep", AsyncMock())
    timeout = APITimeoutError(
        request=httpx.Request("POST", "https://api.openai.com/v1/images/generations")
    )
    call = AsyncMock(side_effect=[timeout, "ready"])
    if image_request:
        with pytest.raises(policy.OpenAIServiceError) as raised:
            await policy.request_openai(
                call, api_key="key", operation="image", image_request=True, attempts=4
            )
        assert raised.value.problem.kind == "timeout"
        call.assert_awaited_once()
    else:
        assert (
            await policy.request_openai(call, api_key="key", operation="text", attempts=2)
            == "ready"
        )
        assert call.await_count == 2


async def test_server_failure_uses_exact_attempt_budget(monkeypatch):
    monkeypatch.setattr(policy.asyncio, "sleep", AsyncMock())
    call = AsyncMock(
        side_effect=sdk_error(503, "server_is_overloaded", "service_unavailable_error")
    )
    with pytest.raises(policy.OpenAIServiceError):
        await policy.request_openai(
            call, api_key="key", operation="image", image_request=True, attempts=2
        )
    assert call.await_count == 2


async def test_auth_gate_is_scoped_to_credentials_and_an_operator_reset_allows_probe():
    failing = AsyncMock(side_effect=sdk_error(401, "invalid_api_key", "authentication_error"))
    with pytest.raises(policy.OpenAIServiceError):
        await policy.request_openai(failing, api_key="old-key", operation="image")
    working = AsyncMock(return_value="ready")
    assert await policy.request_openai(working, api_key="new-key", operation="image") == "ready"
    policy.reset_openai_access("old-key")
    assert await policy.request_openai(working, api_key="old-key", operation="image") == "ready"


async def test_only_one_probe_is_sent_when_billing_cooldown_expires(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(policy, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    failing = AsyncMock(side_effect=sdk_error())
    with pytest.raises(policy.OpenAIServiceError):
        await policy.request_openai(failing, api_key="key", operation="image", quota_cooldown=30)
    clock[0] += 31
    started, release = asyncio.Event(), asyncio.Event()

    async def probe():
        started.set()
        await release.wait()
        return "ready"

    first = asyncio.create_task(policy.request_openai(probe, api_key="key", operation="image"))
    await started.wait()
    duplicate = AsyncMock()
    with pytest.raises(policy.OpenAIServiceError):
        await policy.request_openai(duplicate, api_key="key", operation="text")
    duplicate.assert_not_awaited()
    release.set()
    assert await first == "ready"
    assert policy.check_openai_access("key") is None


@pytest.mark.parametrize(
    "header", [{"retry-after-ms": "1500"}, {"retry-after": "NaN"}, {"retry-after": "-2"}]
)
def test_retry_header_handles_milliseconds_and_invalid_values(header):
    delay = policy.classify_openai_error(sdk_error(headers=header)).retry_after
    expected = 1.5 if "retry-after-ms" in header else None if header["retry-after"] == "NaN" else 0
    assert delay == expected


@pytest.mark.parametrize("lang", ["uk", "ru", "en"])
def test_customer_message_does_not_claim_all_quota_errors_are_empty_balance(lang):
    problem = policy.AIProblem("quota", "project_spend_limit_exceeded", request_id="req_test")
    text = policy.user_message(problem, lang)
    assert "project_spend_limit_exceeded" not in text
    assert "req_test" not in text
    assert "OPENAI_API_KEY" not in text
    assert "project" in policy.operator_message(problem)


async def test_actual_sdk_makes_only_one_http_call_for_quota(tmp_path):
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(
            429,
            headers={"x-request-id": "req_quota"},
            json={
                "error": {
                    "message": "Sensitive prompt must stay private",
                    "type": "insufficient_quota",
                    "code": "project_spend_limit_exceeded",
                }
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    client = AsyncOpenAI(api_key="sdk-key", max_retries=0, http_client=http_client)
    service = object.__new__(ImageGenerationService)
    service.settings = Settings(_env_file=None, openai_api_key="sdk-key", image_retries=4)
    service.openai_client = client
    try:
        for _ in range(2):
            with pytest.raises(QuotaExhaustedError) as raised:
                await service.generate("Photograph of borscht", tmp_path / "dish.jpg")
            assert raised.value.code == "project_spend_limit_exceeded"
        assert len(calls) == 1
        assert not (tmp_path / "dish.jpg").exists()
    finally:
        await client.close()


async def test_actual_sdk_rate_limit_then_validated_jpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(policy.asyncio, "sleep", AsyncMock())
    png = io.BytesIO()
    Image.new("RGB", (1024, 1024), "#735a30").save(png, "PNG")
    calls = []

    def transport(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                429,
                headers={"retry-after": "0"},
                json={
                    "error": {
                        "message": "slow down",
                        "code": "rate_limit_exceeded",
                        "type": "rate_limit_error",
                    }
                },
            )
        return httpx.Response(
            200,
            json={"created": 1, "data": [{"b64_json": base64.b64encode(png.getvalue()).decode()}]},
        )

    client = AsyncOpenAI(
        api_key="key",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
    )
    service = object.__new__(ImageGenerationService)
    service.settings = Settings(_env_file=None, openai_api_key="key", image_retries=2)
    service.openai_client = client
    try:
        result = await service.generate("Photograph", tmp_path / "dish.jpg")
        assert len(calls) == 2
        with Image.open(result) as photo:
            assert photo.format == "JPEG"
    finally:
        await client.close()


async def test_recipe_quota_propagates_correct_reason_without_placeholder(monkeypatch):
    call = AsyncMock(side_effect=sdk_error(code="organization_spend_limit_exceeded"))
    monkeypatch.setattr(
        "app.services.recipe_generator.AsyncOpenAI",
        lambda **kwargs: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=call))
        ),
    )
    service = RecipeGeneratorService(Settings(_env_file=None, openai_api_key="key"))
    with pytest.raises(policy.OpenAIServiceError) as raised:
        await service.generate_menu_details(["Борщ"], "ru")
    assert raised.value.code == "organization_spend_limit_exceeded"
    call.assert_awaited_once()


async def test_renderer_reopens_reference_streams_for_rate_limit_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(policy.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr("app.services.replicate_vision_board.image_cost_usd", lambda *args: 1)
    png = io.BytesIO()
    Image.new("RGB", (700, 700), "#735a30").save(png, "PNG")
    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (700, 700)).save(photo)
    streams = []

    async def edit(**options):
        streams.append([stream.read() for stream in options["image"]])
        if len(streams) == 1:
            raise sdk_error(
                code="rate_limit_exceeded",
                error_type="rate_limit_error",
                headers={"retry-after": "0"},
            )
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(png.getvalue()).decode())],
            usage=object(),
        )

    renderer = ReplicateVisionBoardRenderer(
        output_dir=tmp_path / "output",
        openai_api_key="key",
        client=SimpleNamespace(images=SimpleNamespace(edit=edit)),
    )
    result = await renderer._edit_photos([photo], "Photo", "9:16")
    assert result.size == (700, 700)
    assert streams[0] == streams[1] and len(streams[1][0]) > 100


async def test_legacy_edit_uses_same_billing_policy(tmp_path):
    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (700, 700)).save(photo)
    renderer = object.__new__(WallpaperRenderer)
    renderer.api_key, renderer.model, renderer.output_dir, renderer.max_attempts = (
        "key",
        "gpt-image-1.5",
        tmp_path,
        4,
    )
    call = AsyncMock(side_effect=sdk_error(code="project_spend_limit_exceeded"))
    renderer.client = SimpleNamespace(images=SimpleNamespace(edit=call))
    with pytest.raises(policy.OpenAIServiceError):
        await renderer.edit_image(image_path=photo, prompt="Photo")
    call.assert_awaited_once()


@pytest.fixture
async def menu_db(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "orders.db"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    ready = tmp_path / "ready.jpg"
    Image.new("RGB", (700, 700), "#80654f").save(ready)
    async with factory() as session:
        customer = Customer(
            id=1,
            telegram_user_id=42,
            name="Client",
            phone="+380000",
            language=Language.RU,
            country="Ukraine",
            city="Kyiv",
        )
        session.add(customer)
        session.add(
            Menu(
                id=1,
                customer_id=1,
                status=MenuStatus.QUEUED,
                cover_photo_path="cover.jpg",
                spread_photo_path="spread.jpg",
            )
        )
        for index in range(4):
            session.add(
                MenuItem(
                    id=index + 1,
                    menu_id=1,
                    title=f"Dish {index}",
                    category=ItemCategory.MAIN,
                    position=index + 1,
                    generation_status=GenerationStatus.DONE
                    if index == 0
                    else GenerationStatus.PENDING,
                    image_path=str(ready) if index == 0 else None,
                )
            )
        await session.commit()
    yield factory, ready
    await engine.dispose()


def pipeline_stub(factory, tmp_path):
    pipeline = object.__new__(MenuPipeline)
    pipeline.session_factory = factory
    pipeline.settings = Settings(_env_file=None, admin_telegram_ids=(42,), storage_root=tmp_path)
    pipeline.bot = SimpleNamespace(send_message=AsyncMock())
    pipeline.queue = asyncio.Queue()
    pipeline._scheduled = set()
    pipeline.prompt_builder = SimpleNamespace(build=lambda item: "Photograph")
    pipeline.renderer = SimpleNamespace(render=AsyncMock())
    pipeline.recipe_service = SimpleNamespace(generate_menu_details=AsyncMock())
    pipeline.image_service = SimpleNamespace(
        generate=AsyncMock(
            side_effect=QuotaExhaustedError(
                problem=policy.AIProblem("quota", "project_spend_limit_exceeded")
            )
        )
    )
    return pipeline


async def test_menu_stops_after_first_refusal_preserves_ready_photo_and_can_resume_once(
    menu_db, tmp_path
):
    factory, ready = menu_db
    pipeline = pipeline_stub(factory, tmp_path)
    await pipeline._process(1)
    pipeline.image_service.generate.assert_awaited_once()
    pipeline.recipe_service.generate_menu_details.assert_not_awaited()
    pipeline.renderer.render.assert_not_awaited()
    async with factory() as session:
        menu = await session.get(Menu, 1)
        assert menu.status == MenuStatus.FAILED
        assert "project_spend_limit_exceeded" in menu.error_message
        assert (await session.get(MenuItem, 1)).generation_status == GenerationStatus.DONE
        assert (await session.get(MenuItem, 2)).generation_status == GenerationStatus.FAILED
        assert (await session.get(MenuItem, 3)).generation_status == GenerationStatus.PENDING
    assert ready.exists()
    assert "Администратору" in pipeline.bot.send_message.call_args.args[1]
    assert not await pipeline.retry(1, 999)  # cannot resume another user's paid job
    assert await pipeline.retry(1, 42)
    assert not await pipeline.retry(1, 42)
    assert pipeline.queue.qsize() == 1


async def test_menu_worker_releases_queue_and_dedup_on_unexpected_failure():
    pipeline = object.__new__(MenuPipeline)
    pipeline.queue, pipeline._scheduled = asyncio.Queue(), set()
    pipeline._process = AsyncMock(side_effect=ValueError("processing failed"))
    assert await pipeline.submit(10, 42)
    assert not await pipeline.submit(10, 42)
    worker = asyncio.create_task(pipeline._worker())
    await asyncio.wait_for(pipeline.queue.join(), 1)
    assert pipeline._scheduled == set()
    worker.cancel()
    await asyncio.gather(worker, return_exceptions=True)


async def test_miniapp_failure_keeps_uploads_and_saved_plan_for_same_job_retry(
    tmp_path, monkeypatch
):
    photo = tmp_path / "photo_0.jpg"
    Image.new("RGB", (700, 700)).save(photo)
    settings = Settings(
        _env_file=None, bot_token="123:test", openai_api_key="key", storage_root=tmp_path
    )
    job = {
        "id": "a" * 32,
        "user_id": 42,
        "status": "generating",
        "free": True,
        "goals": ["one"] * 5,
        "language": "ru",
        "style": "dark",
        "order_id": None,
    }
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    monkeypatch.setattr(api, "_read_job", lambda *args: job)
    monkeypatch.setattr(api, "_write_job", lambda *args: None)
    plan = AsyncMock(
        return_value=SimpleNamespace(assignments=[0] * 5, scenes=["scene"] * 5, ai_cost_usd=1)
    )
    monkeypatch.setattr(api, "GoalScenePlanner", lambda settings: SimpleNamespace(plan=plan))
    render = AsyncMock(
        side_effect=policy.OpenAIServiceError(policy.AIProblem("quota", "credit_balance_exhausted"))
    )
    monkeypatch.setattr(
        api,
        "ReplicateVisionBoardRenderer",
        lambda **kwargs: SimpleNamespace(generate_goal_story=render),
    )
    import app.main

    monkeypatch.setattr(app.main.app.state, "bot", None, raising=False)
    await api._generate_gift(42, "a" * 32, [photo], None)
    assert photo.exists() and api._public_job(job)["can_retry"]
    assert "Администратору" in job["error"]
    assert job["plan"]["ai_cost_usd"] == "1"
    job["status"] = "generating"
    await api._generate_gift(42, "a" * 32, [photo], None)
    plan.assert_awaited_once()  # the second attempt does not rebill the plan
    assert render.await_count == 2


async def test_telegram_gift_shows_clear_problem_and_keeps_fsm_data(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, storage_root=tmp_path, admin_telegram_ids=(42,))
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"photo")
    monkeypatch.setattr(wallpaper, "upload_paths", lambda *args: [photo])
    plan = AsyncMock(
        side_effect=policy.OpenAIServiceError(policy.AIProblem("auth", "invalid_api_key"))
    )
    monkeypatch.setattr(wallpaper, "GoalScenePlanner", lambda settings: SimpleNamespace(plan=plan))
    data = {"goals": ["one"] * 5, "lang": "ru"}
    state = SimpleNamespace(
        get_data=AsyncMock(return_value=data), set_state=AsyncMock(), update_data=AsyncMock()
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42, username=None),
        answer=AsyncMock(return_value=SimpleNamespace(delete=AsyncMock())),
    )
    await wallpaper.generate_wallpapers(message, state, settings, AsyncMock())
    assert photo.exists()
    text = message.answer.call_args_list[-1].args[0]
    assert "ключ" in text and "Фото, цели" in text
    assert "invalid_api_key" not in text


async def test_menu_cancellation_records_recoverable_status(menu_db, tmp_path):
    factory, ready = menu_db
    pipeline = pipeline_stub(factory, tmp_path)
    started = asyncio.Event()

    async def pending(*args):
        started.set()
        await asyncio.Event().wait()

    pipeline.image_service.generate = pending
    task = asyncio.create_task(pipeline._process(1))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with factory() as session:
        menu = await session.get(Menu, 1)
        assert menu.status == MenuStatus.FAILED
        assert policy.problem_from_record(menu.error_message).kind == "interrupted"
    assert ready.exists()


async def test_storage_failure_is_not_misreported_as_invalid_openai_image(tmp_path):
    service = object.__new__(ImageGenerationService)
    service.settings = Settings(_env_file=None, openai_api_key="key")
    service._request_image = AsyncMock(return_value=b"image")

    def failed_save(*args):
        raise OSError("disk is full")

    service._save_verified_jpeg = failed_save
    with pytest.raises(policy.OpenAIServiceError) as raised:
        await service.generate("Photo", tmp_path / "dish.jpg")
    assert raised.value.problem.kind == "storage"


async def test_customer_menu_status_sanitizes_legacy_errors_and_retry_checks_owner(
    menu_db, tmp_path, monkeypatch
):
    from starlette.requests import Request

    factory, _ = menu_db
    monkeypatch.setattr(api, "async_session_maker", factory)
    async with factory() as session:
        menu = await session.get(Menu, 1)
        menu.status = MenuStatus.FAILED
        menu.error_message = "Sensitive raw old SDK error: sk-secret-example"
        await session.commit()
    result = await api.menu_status(1, {"id": 42})
    assert (
        result["can_retry"] and "Sensitive" not in result["error"] and "sk-" not in result["error"]
    )
    pipeline = pipeline_stub(factory, tmp_path)
    request = Request(
        {"type": "http", "app": SimpleNamespace(state=SimpleNamespace(pipeline=pipeline))}
    )
    with pytest.raises(api.HTTPException) as wrong_user:
        await api.retry_menu(1, request, {"id": 999})
    assert wrong_user.value.status_code == 404
    result = await api.retry_menu(1, request, {"id": 42})
    assert result["status"] == "queued" and not result["can_retry"]
    with pytest.raises(api.HTTPException) as duplicate:
        await api.retry_menu(1, request, {"id": 42})
    assert duplicate.value.status_code == 409
    assert pipeline.queue.qsize() == 1


async def test_other_safety_codes_are_sanitized_without_neutral_retry():
    call = AsyncMock(
        side_effect=sdk_error(400, "content_policy_violation", "invalid_request_error")
    )
    with pytest.raises(policy.OpenAIServiceError) as raised:
        await policy.request_openai(
            call, api_key="key", operation="image", preserve_safety=True, attempts=4
        )
    assert raised.value.problem.kind == "safety"
    assert "SECRET" not in str(raised.value)
    call.assert_awaited_once()


async def test_gift_retry_reserves_slot_and_reuses_same_saved_job(tmp_path, monkeypatch):
    folder = tmp_path / "gift"
    folder.mkdir()
    (folder / "photo_0.jpg").write_bytes(b"photo")
    job = {
        "id": "a" * 32,
        "status": "failed",
        "ai_error": {"kind": "quota", "code": "insufficient_quota"},
    }
    monkeypatch.setattr(api, "_read_job", lambda *args: job)
    monkeypatch.setattr(api, "_write_job", lambda *args: None)
    monkeypatch.setattr(api, "_job_dir", lambda *args: folder)
    calls = []

    async def generate(*args):
        calls.append(args)

    monkeypatch.setattr(api, "_generate_gift", generate)
    tasks = []
    monkeypatch.setattr(api, "_track", tasks.append)
    api._user_jobs.discard(77)
    try:
        result = await api.retry_gift("a" * 32, {"id": 77, "username": None})
        assert result["status"] == "generating" and "ai_error" not in job
        with pytest.raises(api.HTTPException) as duplicate:
            await api.retry_gift("a" * 32, {"id": 77})
        assert duplicate.value.status_code == 409
        await asyncio.gather(*tasks)
        assert len(calls) == 1 and calls[0][1] == "a" * 32
        assert calls[0][2] == [folder / "photo_0.jpg"]
    finally:
        api._user_jobs.discard(77)
