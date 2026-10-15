"""
==========================================================
FOOD_PORN

Module: Portmone Sandbox Handler
Layer: Telegram Interface

Responsibilities:
    - Verify diagnostic card payments with Portmone server-to-server
    - Restrict the test control to current VIP/admin users
    - Keep sandbox results separate from digital product access
==========================================================
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.repositories import PortmoneSandboxPaymentRepository
from app.services.free_access import has_free_generation_access
from app.services.payment import PaymentService

logger = logging.getLogger(__name__)
router = Router(name="portmone_sandbox")


@router.callback_query(F.data.startswith("portmone_test_check:"))
async def verify_portmone_sandbox(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    try:
        payment_id = int((callback.data or "").partition(":")[2])
    except ValueError:
        await callback.answer("Некорректный номер теста.", show_alert=True)
        return

    allowed = await has_free_generation_access(
        callback.from_user.id,
        getattr(callback.from_user, "username", None),
        settings,
        session_factory,
    )
    if not settings.portmone_test_mode or not allowed:
        await callback.answer("Тест Portmone недоступен.", show_alert=True)
        return

    async with session_factory() as session:
        repository = PortmoneSandboxPaymentRepository(session)
        payment = await repository.get_for_user(payment_id, callback.from_user.id)
        if payment is None:
            await callback.answer("Тестовый платёж не найден.", show_alert=True)
            return
        if payment.status == "paid":
            await callback.answer("✅ Этот тест уже успешно подтверждён.", show_alert=True)
            return
        try:
            verified = await PaymentService(settings).verify_portmone_payment(
                payment.id,
                payment.amount,
                product=f"sandbox_{payment.product}",
            )
        except Exception:
            logger.exception("Portmone sandbox verification failed for payment %s", payment.id)
            await callback.answer(
                "Portmone временно не отвечает. Повторите проверку позже.",
                show_alert=True,
            )
            return
        if verified is None:
            await callback.answer(
                "Платёж пока не подтверждён. Завершите тест на странице Portmone.",
                show_alert=True,
            )
            return
        await repository.mark_paid(payment, verified.payment_id)

    await callback.answer(
        "✅ Тест Portmone пройден. Сумма, заказ и статус подтверждены сервером.",
        show_alert=True,
    )
