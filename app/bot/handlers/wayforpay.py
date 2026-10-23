"""
==========================================================
FOOD_PORN

Module: WayForPay Telegram Handler
Layer: Presentation / Payments

Responsibilities:
    - Recheck a customer-owned WayForPay order server-to-server
    - Deliver digital files only after a signed Approved response
    - Keep repeated button presses idempotent
==========================================================
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.models import FileKind
from app.database.repositories import (
    MenuRepository,
    WallpaperOrderRepository,
    WayForPayPaymentRepository,
)
from app.services.print_bundle import create_print_bundle
from app.services.wayforpay import WayForPayService, apply_verified_payment

logger = logging.getLogger(__name__)
router = Router(name="wayforpay")


async def _deliver_menu(callback: CallbackQuery, menu_id: int, session: AsyncSession) -> bool:
    menu = await MenuRepository(session).get(menu_id, full=True)
    if menu is None or menu.customer.telegram_user_id != callback.from_user.id or not menu.is_paid:
        return False
    files = {file.kind: Path(file.path) for file in menu.files}
    pdf = files.get(FileKind.PRINT_PDF)
    recipe = files.get(FileKind.RECIPE_SHEET)
    if pdf is None or recipe is None or not pdf.is_file() or not recipe.is_file():
        return False
    await callback.message.answer_document(
        FSInputFile(str(pdf)), caption="Ваш готовый электронный буклет 💛"
    )
    await callback.message.answer_document(
        FSInputFile(str(recipe)), caption="Рецепты и список покупок"
    )
    return True


async def _deliver_wallpaper(
    callback: CallbackQuery, order_id: int, session: AsyncSession, settings: Settings
) -> bool:
    order = await WallpaperOrderRepository(session).get_for_user(order_id, callback.from_user.id)
    if order is None or not order.paid:
        return False
    mobile, desktop = Path(order.mobile_path), Path(order.desktop_path)
    if not mobile.is_file() or not desktop.is_file():
        return False
    await callback.message.answer_document(FSInputFile(str(mobile)), caption="Заставка для телефона 💛")
    await callback.message.answer_document(FSInputFile(str(desktop)), caption="Заставка для компьютера 💛")
    try:
        archive = await asyncio.to_thread(
            create_print_bundle,
            order.id,
            mobile,
            desktop,
            width_mm=settings.print_poster_width_mm,
            height_mm=settings.print_poster_height_mm,
            dpi=settings.print_dpi,
        )
        await callback.message.answer_document(
            FSInputFile(str(archive)), caption="Архив для типографии"
        )
    except Exception:
        logger.exception("Could not create WayForPay print bundle for order %s", order.id)
    return True


@router.callback_query(F.data.startswith("check_wayforpay:"))
async def check_wayforpay(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    try:
        payment_id = int((callback.data or "").removeprefix("check_wayforpay:"))
    except ValueError:
        await callback.answer("Некорректный номер платежа.", show_alert=True)
        return

    async with session_factory() as session:
        repository = WayForPayPaymentRepository(session)
        payment = await repository.get_for_user(payment_id, callback.from_user.id)
        if payment is None:
            await callback.answer("Счёт WayForPay не найден.", show_alert=True)
            return
        if payment.status != "approved":
            try:
                payload = await WayForPayService(settings).check_status(payment)
                if not await apply_verified_payment(session, payment, payload):
                    await callback.answer(
                        "WayForPay пока не подтвердил оплату.", show_alert=True
                    )
                    return
            except Exception:
                logger.exception("WayForPay status check failed for %s", payment.order_reference)
                await callback.answer(
                    "Проверка WayForPay временно недоступна. Повторите немного позже.",
                    show_alert=True,
                )
                return

        if not payment.grants_entitlement:
            delivered = True
            await callback.message.answer("🧪 Тестовый платёж WayForPay подтверждён.")
        else:
            numeric_reference = int(payment.reference_id)
            delivered = (
                await _deliver_menu(callback, numeric_reference, session)
                if payment.product == "menu"
                else await _deliver_wallpaper(callback, numeric_reference, session, settings)
            )
        if not delivered:
            await callback.answer(
                "Оплата подтверждена, но файлы пока недоступны. Напишите в поддержку.",
                show_alert=True,
            )
            return
    await callback.answer("Оплата WayForPay подтверждена!")
