"""Verify Telegram payment updates before unlocking any digital order."""
from __future__ import annotations

import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message, PreCheckoutQuery

from app.config import get_settings
from app.database.models import FileKind, Menu
from app.database.session import async_session_maker
from app.services.stars import parse_payload, payment_is_available, record_payment

router = Router(name="stars")
logger = logging.getLogger(__name__)


@router.pre_checkout_query()
async def stars_pre_checkout(query: PreCheckoutQuery) -> None:
    ref = parse_payload(query.invoice_payload)
    valid = (ref is not None and query.currency == "XTR"
             and query.total_amount == ref.stars and query.from_user.id == ref.owner_id)
    try:
        valid = valid and await payment_is_available(async_session_maker, ref)
    except Exception:
        logger.exception("Stars precheckout validation failed")
        valid = False
    await query.answer(ok=bool(valid), error_message=None if valid else
                       "Заказ или цена изменились. Откройте заказ и попробуйте снова.")


@router.message(F.successful_payment)
async def stars_success(message: Message) -> None:
    receipt = message.successful_payment
    ref = parse_payload(receipt.invoice_payload)
    if (ref is None or message.from_user is None or message.from_user.id != ref.owner_id
            or receipt.currency != "XTR" or receipt.total_amount != ref.stars):
        logger.error("Unexpected Stars receipt in message %s", message.message_id)
        return
    charge_id = receipt.telegram_payment_charge_id
    try:
        result = await record_payment(async_session_maker, ref, charge_id)
    except Exception:
        logger.exception("Could not persist Stars charge %s", charge_id)
        await message.answer("Оплата поступила, но выдача задержалась. Напишите /paysupport с номером заказа.")
        return
    if result == "duplicate":
        try:
            await message.bot.refund_star_payment(ref.owner_id, charge_id)
        except Exception:
            logger.exception("Refund of duplicate Stars charge %s failed", charge_id)
            await message.answer("Повторный платёж получен. Напишите /paysupport для возврата.")
        return
    if result == "same":
        return

    if ref.kind == "menu":
        async with async_session_maker() as session:
            menu = await session.get(Menu, ref.order_id)
            await session.refresh(menu, ["files"])
            paths = {file.kind: Path(file.path) for file in menu.files}
        await message.answer("Оплата Stars подтверждена. Полный заказ открыт в Мастерской 💛")
        for kind in (FileKind.PRINT_PDF, FileKind.RECIPE_SHEET):
            path = paths.get(kind)
            if path and path.is_file():
                try:
                    await message.answer_document(FSInputFile(str(path)))
                except Exception:
                    logger.exception("Could not send paid menu file %s", path)
    else:
        # Update the durable Mini App job so an owner sees the files on refresh.
        root = get_settings().storage_root / "miniapp_jobs" / str(ref.owner_id)
        if root.is_dir():
            from app.miniapp.api import _read_job, _write_job
            for folder in root.iterdir():
                if not folder.is_dir():
                    continue
                try:
                    job = _read_job(ref.owner_id, folder.name)
                    if job.get("order_id") == ref.order_id:
                        job["status"] = "ready"
                        _write_job(ref.owner_id, folder.name, job)
                except Exception:
                    logger.exception("Could not update Mini App job %s", folder.name)
        await message.answer("Оплата Stars подтверждена. Ваш подарок и файлы для печати открыты 💛")


@router.message(Command("paysupport"))
async def stars_support(message: Message) -> None:
    username = get_settings().admin_username.strip().lstrip("@")
    contact = f"@{username}" if username else "ответным сообщением в этот бот"
    await message.answer(f"Вопрос по оплате? Укажите номер заказа и ID платежа из чека: {contact}.")
