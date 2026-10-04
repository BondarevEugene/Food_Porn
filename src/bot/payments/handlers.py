# src/bot/payments/handlers.py
from aiogram import F, Router
from aiogram.types import Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

# Предполагается импорт вашего сервиса биллинга из предыдущих модулей
from src.billing.service import BillingService

payments_router = Router()


@payments_router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    """
    ШАГ 2: Telegram за доли секунды до списания денег спрашивает бота:
    "Всё ок? Пользователь может платить?"
    Здесь можно сделать быструю проверку (например, не заблокирован ли юзер).
    """
    await pre_checkout_query.answer(ok=True)


@payments_router.message(F.successful_payment)
async def process_successful_payment(message: Message, db_session: AsyncSession):
    """
    ШАГ 3: Деньги успешно списаны через Portmone в интерфейсе Telegram.
    Деньги поступают на ваш мерчант Portmone, а бот получает уведомление.
    """
    payment_info = message.successful_payment
    telegram_user_id = str(message.from_user.id)

    # Сумма в копейках, пришедшая от Telegram
    amount_paid = payment_info.total_amount
    payload = payment_info.invoice_payload  # Здесь наш уникальный ID (например, order_123)

    # Вызываем наш бэкенд-биллинг для зачисления средств на баланс FoodPorn
    billing_service = BillingService(db_session)
    await billing_service.deposit_funds(
        owner_id=telegram_user_id,
        amount=amount_paid,
        reference_id=payload,
        description="Пополнение через Telegram Stars / Portmone"
    )

    await message.answer(
        f"✅ Оплачено успешно! На ваш баланс зачислено {amount_paid / 100:.2f} UAH.\n"
        "Можете продолжать генерацию контента в FoodPorn! 🚀"
    )