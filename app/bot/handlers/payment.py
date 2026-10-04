"""Unlock only an order paid to our merchant for its saved price."""
from __future__ import annotations

import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.models import FileKind, MenuStatus
from app.database.repositories import MenuRepository
from app.services.payment import PaymentService
from app.services.printshop import PrintshopService

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("check_payment_"))
async def verify_payment_callback(
    callback: CallbackQuery, settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    try:
        menu_id = int((callback.data or "").removeprefix("check_payment_"))
    except ValueError:
        await callback.answer("Некорректный номер заказа.", show_alert=True)
        return

    async with session_factory() as session:
        repo = MenuRepository(session)
        menu = await repo.get(menu_id, full=True)
        if not menu or menu.customer.telegram_user_id != callback.from_user.id:
            await callback.answer("Заказ не найден.", show_alert=True)
            return
        if not menu.is_paid and (menu.status != MenuStatus.WAITING_FOR_PAYMENT or menu.price_amount is None):
            await callback.answer("Для заказа пока нет действующего счёта.", show_alert=True)
            return

        if not menu.is_paid:
            if menu.stars_amount:
                await callback.answer("Оплата Stars ещё обрабатывается Telegram.", show_alert=True)
                return
            try:
                verified = await PaymentService(settings).verify_portmone_payment(menu_id, menu.price_amount)
            except Exception:
                logger.exception("Payment verification failed for menu %s", menu_id)
                await callback.answer("Проверка оплаты временно недоступна. Повторите позже.", show_alert=True)
                return
            if verified is None:
                await callback.answer("Оплата пока не подтверждена Portmone.", show_alert=True)
                return

        pdf = next((Path(f.path) for f in menu.files if f.kind == FileKind.PRINT_PDF), None)
        recipe = next((Path(f.path) for f in menu.files if f.kind == FileKind.RECIPE_SHEET), None)
        if pdf is None or not pdf.is_file() or recipe is None or not recipe.is_file():
            logger.error("Paid menu %s missing saved output files", menu_id)
            await callback.answer("Платёж получен, но файлы недоступны. Напишите в поддержку.", show_alert=True)
            return

        if not menu.is_paid:
            await repo.mark_as_paid(menu_id, verified.payment_id, "portmone")
        await callback.answer("Оплата подтверждена!")
        await callback.message.answer_document(FSInputFile(str(pdf)), caption="Ваш готовый буклет для печати")
        await callback.message.answer_document(FSInputFile(str(recipe)), caption="Рецепты и список покупок")

        customer_info = f"Telegram User ID: {callback.from_user.id}"
        sent = False
        if menu.payment_system != "telegram_stars" and menu.status != MenuStatus.SENT_TO_PRINTSHOP:
            sent = await PrintshopService(settings).dispatch_to_printshop(menu_id, pdf, customer_info)
        if sent:
            await repo.mark_sent_to_printshop(menu_id)
            await callback.message.answer("Заказ передан в типографию.")
