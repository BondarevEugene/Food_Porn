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
from app.services.wayforpay import (
    WayForPayService,
    apply_verified_payment,
)

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
        FSInputFile(str(pdf)), caption="Р’Р°С€ РіРѕС‚РѕРІС‹Р№ СЌР»РµРєС‚СЂРѕРЅРЅС‹Р№ Р±СѓРєР»РµС‚ рџ’›"
    )
    await callback.message.answer_document(
        FSInputFile(str(recipe)), caption="Р РµС†РµРїС‚С‹ Рё СЃРїРёСЃРѕРє РїРѕРєСѓРїРѕРє"
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
    await callback.message.answer_document(FSInputFile(str(mobile)), caption="Р—Р°СЃС‚Р°РІРєР° РґР»СЏ С‚РµР»РµС„РѕРЅР° рџ’›")
    await callback.message.answer_document(FSInputFile(str(desktop)), caption="Р—Р°СЃС‚Р°РІРєР° РґР»СЏ РєРѕРјРїСЊСЋС‚РµСЂР° рџ’›")
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
            FSInputFile(str(archive)), caption="РђСЂС…РёРІ РґР»СЏ С‚РёРїРѕРіСЂР°С„РёРё"
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
        await callback.answer("РќРµРєРѕСЂСЂРµРєС‚РЅС‹Р№ РЅРѕРјРµСЂ РїР»Р°С‚РµР¶Р°.", show_alert=True)
        return

    async with session_factory() as session:
        repository = WayForPayPaymentRepository(session)
        payment = await repository.get_for_user(payment_id, callback.from_user.id)
        if payment is None:
            await callback.answer("РЎС‡С‘С‚ WayForPay РЅРµ РЅР°Р№РґРµРЅ.", show_alert=True)
            return
        if payment.status != "approved":
            try:
                payload = await WayForPayService(settings).check_status(payment)

                # False can mean either provider rejection or an already
                # paid order. Inspect the persisted provider status separately.
                await apply_verified_payment(session, payment, payload)

                if payment.status != "approved":
                    await callback.answer(
                        "WayForPay РїРѕРєР° РЅРµ РїРѕРґС‚РІРµСЂРґРёР» РѕРїР»Р°С‚Сѓ.",
                        show_alert=True,
                    )
                    return

            except Exception:
                logger.exception(
                    "WayForPay status check failed for %s",
                    payment.order_reference,
                )
                await callback.answer(
                    "РџСЂРѕРІРµСЂРєР° WayForPay РІСЂРµРјРµРЅРЅРѕ РЅРµРґРѕСЃС‚СѓРїРЅР°. "
                    "РџРѕРІС‚РѕСЂРёС‚Рµ РЅРµРјРЅРѕРіРѕ РїРѕР·Р¶Рµ.",
                    show_alert=True,
                )
                return
            await callback.answer(
                "РџР»Р°С‚С‘Р¶ WayForPay РїРѕРґС‚РІРµСЂР¶РґС‘РЅ, РЅРѕ Р·Р°РєР°Р· СѓР¶Рµ РѕРїР»Р°С‡РµРЅ "
                "РґСЂСѓРіРёРј СЃРїРѕСЃРѕР±РѕРј. РџРѕРІС‚РѕСЂРЅРѕ РѕРїР»Р°С‡РёРІР°С‚СЊ РЅРµ РЅСѓР¶РЅРѕ. "
                "Р•СЃР»Рё РґРµРЅСЊРіРё СЃРїРёСЃР°РЅС‹ РґРІР°Р¶РґС‹, РѕР±СЂР°С‚РёС‚РµСЃСЊ РІ РїРѕРґРґРµСЂР¶РєСѓ.",
                show_alert=True,
            )
            return

        if not payment.grants_entitlement:
            await callback.message.answer(
                "Тестовый платёж WayForPay подтверждён."
            )
        elif payment.product == "menu":
            await _deliver_menu(
                callback, int(payment.reference_id), session
            )
        elif payment.product == "wallpaper":
            await _deliver_wallpaper(
                callback,
                int(payment.reference_id),
                session,
                settings,
            )
        else:
            logger.error(
                "Unsupported WayForPay product %r for payment %s",
                payment.product,
                payment.order_reference,
            )
            await callback.answer(
                "РќРµРёР·РІРµСЃС‚РЅС‹Р№ С‚РёРї Р·Р°РєР°Р·Р°. РћР±СЂР°С‚РёС‚РµСЃСЊ РІ РїРѕРґРґРµСЂР¶РєСѓ.",
                show_alert=True,
            )
            return
