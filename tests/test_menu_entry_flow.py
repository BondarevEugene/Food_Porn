"""
==========================================================
FOOD_PORN

Module: Menu Entry Flow Tests
Layer: Quality Assurance

Responsibilities:
    - Keep the food-product entry point actionable
    - Prevent unhandled text immediately after product selection
    - Preserve single-dish and bulk-list input modes
==========================================================
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.bot.handlers import menu, start
from app.database.models import MenuStatus


def make_empty_menu() -> SimpleNamespace:
    return SimpleNamespace(
        id=71,
        status=MenuStatus.DRAFT,
        items=[],
        cover_photo_path=None,
        spread_photo_path=None,
    )


def callback_values(markup: object) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_menu_dashboard_offers_single_and_bulk_input() -> None:
    callbacks = callback_values(menu.build_dashboard_kb(make_empty_menu()))

    assert any("pick_category" in value for value in callbacks)
    assert any("bulk_items" in value for value in callbacks)
    assert any("requirements" in value for value in callbacks)
    assert "ignore" not in callbacks


@pytest.mark.asyncio
async def test_legacy_unavailable_generation_button_is_answered() -> None:
    callback = SimpleNamespace(answer=AsyncMock())

    await menu.explain_legacy_generation_requirements(callback)

    callback.answer.assert_awaited_once_with(
        "Для генерации добавьте минимум одно блюдо и загрузите два фото: "
        "для обложки и разворота.",
        show_alert=True,
    )


@pytest.mark.asyncio
async def test_food_product_entry_opens_dashboard(monkeypatch: pytest.MonkeyPatch) -> None:
    created_menu = make_empty_menu()

    class Session:
        async def __aenter__(self) -> Session:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

    class Repository:
        def __init__(self, _session: object) -> None:
            pass

        async def create(self, _customer: object) -> SimpleNamespace:
            return SimpleNamespace(id=created_menu.id)

        async def get(self, _menu_id: int, *, full: bool = False) -> SimpleNamespace:
            assert full is True
            return created_menu

    monkeypatch.setattr(start, "async_session_maker", lambda: Session())
    monkeypatch.setattr(start, "MenuRepository", Repository)

    message = SimpleNamespace(answer=AsyncMock(), from_user=SimpleNamespace(id=725003786))
    state = SimpleNamespace(update_data=AsyncMock())

    await start._send_food_start(message, state, customer=SimpleNamespace(id=1))

    state.update_data.assert_awaited_once_with(menu_id=created_menu.id)
    message.answer.assert_awaited_once()
    sent_text = message.answer.await_args.args[0]
    sent_markup = message.answer.await_args.kwargs["reply_markup"]
    assert "Гастрономический сет" in sent_text
    assert any("bulk_items" in value for value in callback_values(sent_markup))
