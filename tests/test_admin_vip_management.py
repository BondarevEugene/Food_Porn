"""Telegram admin regressions for safe, owner-only VIP composition changes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import admin


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("@Voloshka0602", "voloshka0602"),
        ("bondarev_e", "bondarev_e"),
        ("https://t.me/MenuDishesForLove", "menudishesforlove"),
    ],
)
def test_normalize_vip_username(value, expected):
    assert admin.normalize_vip_username(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "user-name", "https://example.com/user"])
def test_normalize_vip_username_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        admin.normalize_vip_username(value)


def test_settings_keyboard_shows_vip_controls_only_to_owner():
    data = {
        "values": {
            "menu_price_uah": "5.00",
            "menu_price_stars": "1",
            "gift_price_stars": "1",
            "usd_exchange_rate": "41.50",
        }
    }
    owner_callbacks = {
        button.callback_data
        for row in admin.settings_keyboard(data, owner=True).inline_keyboard
        for button in row
    }
    vip_callbacks = {
        button.callback_data
        for row in admin.settings_keyboard(data, owner=False).inline_keyboard
        for button in row
    }
    assert {"admin_vip_add", "admin_vip_remove"} <= owner_callbacks
    assert "admin_paid_test_toggle" in owner_callbacks
    assert "admin_vip_add" not in vip_callbacks
    assert "admin_vip_remove" not in vip_callbacks
    assert "admin_paid_test_toggle" not in vip_callbacks


@pytest.mark.asyncio
async def test_non_owner_cannot_open_vip_mutation(monkeypatch):
    monkeypatch.setattr(admin, "get_settings", lambda: SimpleNamespace(admin_telegram_ids=(42,)))
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=99),
        answer=AsyncMock(),
    )
    assert not await admin.require_owner(callback)
    callback.answer.assert_awaited_once_with(
        "Изменять VIP может только владелец из ADMIN_TELEGRAM_IDS.",
        show_alert=True,
    )
