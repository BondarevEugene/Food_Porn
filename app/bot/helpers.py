"""
==========================================================
FOOD_PORN

Module: Telegram Interface Helpers
Layer: Presentation

Responsibilities:
    - Shared utilities for Telegram handlers
    - Customer authentication and session touching
==========================================================
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Customer, ItemCategory
from app.database.repositories import CustomerRepository

# Заглушка для обратной совместимости со старыми модулями
ITEM_PLAN = [
    (ItemCategory.MAIN, 1, "main"),
]


def item_question(language: str, category_index: int, position: int) -> str:
    """Заглушка для обратной совместимости."""
    return f"Позиция #{position}"


async def current_customer(session: AsyncSession, telegram_user_id: int) -> Customer | None:
    """
    Ищет клиента в базе по его Telegram ID.
    Если находит — обновляет время его последней активности (last_seen_at).
    """
    repo = CustomerRepository(session)
    customer = await repo.by_telegram_id(telegram_user_id)

    if customer:
        await repo.touch(customer)

    return customer

