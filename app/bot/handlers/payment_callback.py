"""
==========================================================
FOOD_PORN

Module: Payment Callback Handler
Layer: Bot / Handlers

Responsibilities:
    - Handle payment confirmation callbacks from users
    - Unlock production PDF and plain recipe sheet
    - Dispatch files to printshop automatically
==========================================================
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile
from app.services.printshop import PrintshopService

from app.config import get_settings

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("check_payment_"))
async def verify_payment_callback(callback: CallbackQuery) -> None:
    """Проверяет статус оплаты и в случае успеха выдает чистый файл и отправляет в типографию."""
    menu_id = int(callback.data.split("_")[-1])
    settings = get_settings()

    # В реальном проекте здесь идет запрос к API Portmone/Redsys для проверки статуса транзакции.
    # Для демонстрации считаем, что оплата подтверждена пользователем.
    is_paid = True

    if not is_paid:
        await callback.answer("Оплата еще не поступила. Пожалуйста, завершите платеж.", show_alert=True)
        return

    await callback.message.answer(
        "✅ <b>Оплата успешно подтверждена!</b>\n\nГенерируем ваш чистый буклет и кулинарную шпаргалку...",
        parse_mode="HTML")

    # Пути к чистым файлам
    production_pdf = settings.generated_dir / str(menu_id) / f"food_porn_menu_{menu_id}_production.pdf"
    recipe_sheet = settings.generated_dir / str(menu_id) / f"food_porn_recipe_sheet_{menu_id}.pdf"

    # 1. Отправляем чистый PDF-буклет без водяных знаков клиенту
    if production_pdf.exists():
        await callback.message.answer_document(
            document=FSInputFile(str(production_pdf)),
            caption="🎉 <b>Ваш официальный гастрономический сет (без водяных знаков):</b>",
            parse_mode="HTML"
        )

    # 2. Отправляем простой пошаговый рецепт на листе А4
    if recipe_sheet.exists():
        await callback.message.answer_document(
            document=FSInputFile(str(recipe_sheet)),
            caption="🍳 <b>Ваша пошаговая кулинарная шпаргалка (формат А4 для печати):</b>",
            parse_mode="HTML"
        )

    # 3. Автоматически отправляем заказ в типографию на печать
    printshop_service = PrintshopService(settings)
    customer_info = f"Telegram ID: {callback.from_user.id} (@{callback.from_user.username})"

    if production_pdf.exists():
        await printshop_service.dispatch_to_printshop(menu_id, production_pdf, customer_info)
        await callback.message.answer(
            "🖨 <i>Ваш заказ успешно передан в нашу типографию в обработку! Скоро начнется печать.</i>",
            parse_mode="HTML")

    await callback.answer()
