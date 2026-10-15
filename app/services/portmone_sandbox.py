"""
==========================================================
FOOD_PORN

Module: Portmone Sandbox Offers
Layer: Application Service

Responsibilities:
    - Create isolated one-hryvnia diagnostic payment attempts
    - Expose hosted Portmone checkout only to the VIP/admin flow
    - Never unlock or alter a digital product entitlement
==========================================================
"""

from __future__ import annotations

import logging
from decimal import Decimal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.repositories import PortmoneSandboxPaymentRepository
from app.services.payment import PaymentService

logger = logging.getLogger(__name__)


def _copy(product: str, language: str, amount: Decimal) -> tuple[str, str, str]:
    is_uk = str(language).lower() in {"uk", "ukrainian"}
    name = "гастрономічного сету" if product == "menu" else "цифрового подарунка"
    if not is_uk:
        name = "гастрономического сета" if product == "menu" else "цифрового подарка"
    amount_text = f"{amount:.2f} ₴"
    if is_uk:
        body = (
            f"🧪 <b>Тест Portmone для {name}</b>\n\n"
            f"Діагностична сума: <b>{amount_text}</b>. Це не купівля: файли вже доступні "
            "за VIP-доступом, а результат лише перевіряє тестовий платіжний контур."
        )
        return body, f"💳 Тестова оплата · {amount_text}", "🔄 Перевірити тест"
    body = (
        f"🧪 <b>Тест Portmone для {name}</b>\n\n"
        f"Диагностическая сумма: <b>{amount_text}</b>. Это не покупка: файлы уже доступны "
        "по VIP-доступу, а результат только проверяет тестовый платёжный контур."
    )
    return body, f"💳 Тестовая оплата · {amount_text}", "🔄 Проверить тест"


async def send_portmone_sandbox_offer(
    *,
    bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    telegram_user_id: int,
    product: str,
    reference_id: str,
    language: str,
) -> bool:
    """Create and send a hosted sandbox checkout; failures never break delivery."""
    service = PaymentService(settings)
    if not settings.portmone_test_mode or not service.portmone_ready:
        return False

    amount = Decimal(str(settings.portmone_test_amount_uah)).quantize(Decimal("0.01"))
    try:
        async with session_factory() as session:
            repository = PortmoneSandboxPaymentRepository(session)
            payment = await repository.create(
                telegram_user_id=telegram_user_id,
                product=product,
                reference_id=str(reference_id),
                amount=amount,
            )
            try:
                url = await service.create_portmone_invoice(
                    payment.id,
                    amount,
                    f"TEST ONLY: Food_Porn {product} #{reference_id}",
                    product=f"sandbox_{product}",
                )
            except Exception as exc:
                await repository.mark_failed(payment, str(exc))
                logger.exception("Could not create Portmone sandbox invoice %s", payment.id)
                return False
    except Exception:
        logger.exception("Could not create Portmone sandbox checkout")
        return False

    body, pay_text, check_text = _copy(product, language, amount)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=pay_text, url=url)],
            [
                InlineKeyboardButton(
                    text=check_text,
                    callback_data=f"portmone_test_check:{payment.id}",
                )
            ],
        ]
    )
    try:
        await bot.send_message(
            chat_id=telegram_user_id,
            text=body,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Could not send Portmone sandbox offer to user %s", telegram_user_id)
        return False
    return True
