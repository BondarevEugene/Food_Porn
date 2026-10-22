"""The gift reveal and the paid menu plan should stay useful and private."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app.database.models import FileKind, Language, MenuStatus
from app.locales.messages import t
from app.main import app
from app.miniapp import api
from app.services.evening_plan import build_evening_plan, save_evening_plan
from app.services.replicate_vision_board import ReplicateVisionBoardRenderer


def test_romantic_menu_copy_and_print_layout(tmp_path: Path, monkeypatch) -> None:
    for code in ("uk", "ru", "en"):
        letter = t("love_letter", code)
        assert len(letter.split(".")) >= 4
        assert len(letter) > 190
    from app.render.booklet import BookletRenderer
    monkeypatch.setattr(BookletRenderer, "DPI", 72)
    renderer = BookletRenderer(tmp_path)
    outside = Image.new("RGB", (renderer.page_w, renderer.page_h), "#1e1a19")
    inside = outside.copy()
    menu = SimpleNamespace(customer=SimpleNamespace(language=Language.UK))
    seen = []
    original = renderer._fit_text

    def capture(draw, text, box, font, fill, max_lines=2):
        seen.append(text)
        return original(draw, text, box, font, fill, max_lines)

    monkeypatch.setattr(renderer, "_fit_text", capture)
    box = (renderer.bleed, renderer.bleed, renderer.bleed + renderer.panel_w,
           renderer.bleed + renderer.trim_h)
    renderer._draw_back_cover(outside, box, menu)
    renderer._draw_inside_letter(inside, box, menu)
    assert seen.count(t("love_letter", "uk")) == 2


def test_five_wishes_are_rendered_on_both_photo_styles(tmp_path: Path, monkeypatch) -> None:
    from app.services import replicate_vision_board as board
    monkeypatch.setattr(board, "SIZES", {"9:16": (540, 960), "16:9": (960, 540)})
    renderer = ReplicateVisionBoardRenderer(output_dir=tmp_path)
    goals = ["Море", "Дім", "Любов", "Радість", "Подорож"]
    for ratio, color in (("9:16", "#f1e5cf"), ("16:9", "#1c1b1b")):
        image = Image.new("RGB", board.SIZES[ratio], color)
        before = image.copy()
        renderer._render_goal_labels(image, goals, ratio)
        assert image.tobytes() != before.tobytes()
    long_goal = Image.new("RGB", (540, 960), "#181918")
    renderer._render_goal_labels(long_goal, ["Довге бажання про наше спільне майбутнє " * 12] * 5, "9:16")


def test_evening_plan_has_real_recipes_and_reversible_checklist_storage(tmp_path: Path) -> None:
    items = [SimpleNamespace(title=title, category=category, position=position)
             for position, (title, category) in enumerate((
                 ("Steak", "main"), ("Salad", "salad"), ("Tea", "drink")), 1)]
    details = {item.title: {"ingredients": ["Water 1 l"], "recipe": "Prepare and serve",
                            "prep_minutes": 10, "cook_minutes": 5} for item in items}
    plan = build_evening_plan(items, details, ["Water 3 l"], "en")
    assert [entry["title"] for entry in plan["serve"]] == ["Salad", "Steak", "Tea"]
    assert all(entry["recipe"] == "Prepare and serve" for entry in plan["prepare"])
    path = save_evening_plan(tmp_path / "evening_plan.json", plan)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved["serve"]) == len(saved["prepare"]) == 3


@pytest.mark.asyncio
async def test_unpaid_share_token_does_not_expose_recipient_media(monkeypatch) -> None:
    token = "a" * 32
    link = SimpleNamespace(kind="menu", reference_id="45", owner_telegram_id=42)
    menu = SimpleNamespace(is_paid=False, status=MenuStatus.WAITING_FOR_PAYMENT)

    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def get(self, model, key): return link if model is api.ShareLink else menu

    monkeypatch.setattr(api, "async_session_maker", lambda: Session())
    with pytest.raises(HTTPException) as exc:
        await api._shared_gift(token)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as media_exc:
        await api.shared_gift_media(token, "download")
    assert media_exc.value.status_code == 404


def test_paid_share_opens_envelope_and_only_the_saved_media(tmp_path: Path, monkeypatch) -> None:
    token = "c" * 32
    picture = tmp_path / "outside.jpg"
    picture.write_bytes(b"jpeg preview")
    pdf = tmp_path / "menu.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    link = SimpleNamespace(kind="menu", reference_id="45", owner_telegram_id=42)
    menu = SimpleNamespace(is_paid=True, status=MenuStatus.COMPLETED,
                           customer=SimpleNamespace(language=Language.RU),
                           files=[SimpleNamespace(kind=FileKind.PREVIEW_OUTSIDE, path=str(picture)),
                                  SimpleNamespace(kind=FileKind.PRINT_PDF, path=str(pdf))],
                           items=[SimpleNamespace(title="Ужин")])

    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def get(self, model, _key): return link if model is api.ShareLink else menu
        async def refresh(self, *_): pass

    monkeypatch.setattr(api, "async_session_maker", lambda: Session())
    with TestClient(app) as client:
        assert client.get(f"/miniapp/open/{token}").status_code == 200
        data = client.get(f"/miniapp/open/{token}/data").json()
        assert data == {"kind": "menu", "language": "ru", "items": ["Ужин"], "has_inside": False}
        assert client.get(f"/miniapp/open/{token}/media/cover").content == b"jpeg preview"
        assert client.get(f"/miniapp/open/{token}/media/download").content == b"%PDF-1.7"
        assert client.get(f"/miniapp/open/{token}/media/other").status_code == 404


@pytest.mark.asyncio
async def test_native_share_keeps_a_stable_bot_deep_link(monkeypatch) -> None:
    token = "b" * 32
    link = SimpleNamespace(token=token)

    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def scalar(self, _query): return link

    class Bot:
        async def get_me(self): return SimpleNamespace(username="Example_bot")
        async def save_prepared_inline_message(self, **kwargs):
            assert kwargs["user_id"] == 9
            assert f"share_{token}" in kwargs["result"].input_message_content.message_text
            return SimpleNamespace(id="prepared123")

    monkeypatch.setattr(api, "async_session_maker", lambda: Session())
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(miniapp_url="https://test.example/miniapp"))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(bot=Bot())))
    result = await api._create_share(9, "gift", "d" * 32, request)
    assert result["prepared_message_id"] == "prepared123"
    assert result["url"] == f"https://t.me/Example_bot?start=share_{token}"
    assert result["present_url"] == f"https://test.example/miniapp/open/{token}"


def test_shared_page_requires_a_valid_token() -> None:
    with TestClient(app) as client:
        assert client.get("/miniapp/open/invalid").status_code == 404
        assert client.get("/miniapp/static/present.js").status_code == 200
        assert client.get("/miniapp/api/menus/45/evening").status_code == 401
