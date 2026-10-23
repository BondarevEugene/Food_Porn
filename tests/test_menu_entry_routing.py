"""
==========================================================
FOOD_PORN

Module: Menu Entry Routing Tests
Layer: Regression Tests

Responsibilities:
    - Verify that a newly created menu waits for the first dish
    - Verify that incomplete generation requirements are explained
==========================================================
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.menu import (
    PremiumMenuStates,
    begin_menu_entry,
    explain_generation_requirements,
)
from app.database.models import ItemCategory


@pytest.mark.asyncio
async def test_begin_menu_entry_activates_first_dish_state() -> None:
    state = AsyncMock()

    await begin_menu_entry(state, menu_id=42)

    state.set_state.assert_awaited_once_with(PremiumMenuStates.waiting_for_dish_list)
    state.update_data.assert_awaited_once_with(
        menu_id=42,
        category=ItemCategory.MAIN.value,
    )


@pytest.mark.asyncio
async def test_incomplete_generation_button_shows_requirements() -> None:
    callback = SimpleNamespace(answer=AsyncMock())

    await explain_generation_requirements(callback)

    callback.answer.assert_awaited_once_with(
        "Добавьте хотя бы одно блюдо и загрузите фото обложки и разворота.",
        show_alert=True,
    )
