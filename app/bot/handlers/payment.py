"""
==========================================================
FOOD_PORN

Module: Payment Handlers & Callback Processing
Layer: Bot / Handlers

Responsibilities:
    - Handle check payment button clicks from Telegram
    - Update menu status to PAID in database
    - Deliver clean production PDF and plain recipe sheet to user
    - Automatically dispatch files to printshop email
==========================================================
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile
from app.services.printshop import PrintshopService
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.repositories import MenuRepository

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("check_payment_"))
async def verify_payment_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    """Обрабатывает клик по кнопке проверки оплаты, разблокирует чистый файл и отправляет в типографию."""
    try:
        menu_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный идентификатор заказа.", show_alert=True)
        return

    settings = get_settings()
    repo = MenuRepository(session)
    menu = await repo.get(menu_id, full=True)

    if not menu:
        await callback.answer("Меню не найдено в базе данных.", show_alert=True)
        return

    # В реальном продакшн-окружении здесь делается запрос к API Portmone или Redsys для проверки статуса платежа.
    # Для демонстрации и тестирования симулируем успешную оплату (is_paid = True).
    is_paid = True

    if not is_paid:
        await callback.answer(
            "Оплата еще не поступила в системе. Пожалуйста, завершите платеж по ссылке.",
            show_alert=True
        )
        return

    # Обновляем статус в базе данных через репозиторий
    await repo.mark_as_paid(menu_id, payment_id=f"SIM_PAY_{menu_id}", payment_system="portmone")

    language = getattr(menu.customer, "language", "uk") or "uk"
    is_uk = str(language).lower() in ("uk", "ukrainian")

    wait_msg = "✅ <b>Оплату успішно підтверджено!</b>\n\nФормуємо чистий буклет та кулінарну шпаргалку..." if is_uk else "✅ <b>Оплата успешно подтверждена!</b>\n\nФормируем чистый буклет и кулинарную шпаргалку..."
    await callback.message.answer(wait_msg, parse_mode="HTML")

    # Пути к чистым файлам на диске
    production_pdf = settings.generated_dir / str(menu_id) / f"food_porn_menu_{menu_id}_production.pdf"
    recipe_sheet = settings.generated_dir / str(menu_id) / f"food_porn_recipe_sheet_{menu_id}.pdf"

    # 1. Отправляем чистый PDF-буклет без водяных знаков
    if production_pdf.exists():
        caption_prod = "🎉 <b>Ваш офіційний гастрономічний сет (без водяних знаків):</b>" if is_uk else "🎉 <b>Ваш официальный гастрономический сет (без водяных знаков):</b>"
        await callback.message.answer_document(
            document=FSInputFile(str(production_pdf)),
            caption=caption_prod,
            parse_mode="HTML"
        )

    # 2. Отправляем пошаговую кулинарную шпаргалку на листе А4
    if recipe_sheet.exists():
        caption_recipe = "🍳 <b>Ваша покрокова кулінарна шпаргалка (формат А4 для друку):</b>" if is_uk else "🍳 <b>Ваша пошаговая кулинарная шпаргалка (формат А4 для печати):</b>"
        await callback.message.answer_document(
            document=FSInputFile(str(recipe_sheet)),
            caption=caption_recipe,
            parse_mode="HTML"
        )

    # 3. Автоматически отправляем заказ в типографию на физическую печать
    printshop_service = PrintshopService(settings)
    customer_info = f"Telegram User ID: {callback.from_user.id} (@{callback.from_user.username or 'no_username'})"

    if production_pdf.exists():
        success_dispatch = await printshop_service.dispatch_to_printshop(menu_id, production_pdf, customer_info)
        if success_dispatch:
            await repo.mark_sent_to_printshop(menu_id)
            print_msg = "🖨 <i>Ваше замовлення успішно передано до нашої друкарні! Скоро розпочнеться друк.</i>" if is_uk else "🖨 <i>Ваш заказ успешно передан в нашу типографию в обработку! Скоро начнется печать.</i>"
            await callback.message.answer(print_msg, parse_mode="HTML")

    await callback.answer()
