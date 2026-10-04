# app/services/broadcast_service.py
import logging
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import Customer, Menu, MenuStatus

logger = logging.getLogger(__name__)


async def get_target_users(db: AsyncSession, segment: str = "all") -> list[int]:
    """
    Возвращает список Telegram ID пользователей в зависимости от выбранного сегмента:
    - 'all': все зарегистрированные клиенты
    - 'unpaid': клиенты, у которых есть заказы со статусом DRAFT / WAITING_FOR_PAYMENT (брошенные корзины)
    - 'paid': клиенты, у которых есть успешно оплаченные заказы
    """
    if segment == "unpaid":
        query = (
            select(Customer.telegram_user_id)
            .join(Menu, Customer.id == Menu.customer_id)
            .where(Menu.status.in_([MenuStatus.DRAFT, MenuStatus.WAITING_FOR_PAYMENT]))
            .distinct()
        )
    elif segment == "paid":
        query = (
            select(Customer.telegram_user_id)
            .join(Menu, Customer.id == Menu.customer_id)
            .where(Menu.status == MenuStatus.PAID)
            .distinct()
        )
    else:  # 'all'
        query = select(Customer.telegram_user_id).distinct()

    result = await db.execute(query)
    return list(result.scalars().all())


async def execute_broadcast(bot: Bot, db: AsyncSession, text_content: str, segment: str = "all") -> tuple[int, int]:
    """
    Выполняет рассылку сообщений по выбранному сегменту.
    Возвращает кортеж: (успешно отправлено, ошибок/заблокировано).
    """
    user_ids = await get_target_users(db, segment)
    success_count = 0
    fail_count = 0

    for user_id in user_ids:
        try:
            await bot.send_message(chat_id=user_id, text=text_content, parse_mode="HTML")
            success_count += 1
        except Exception as e:
            logger.warning(f"Не удалось отправить рассылку пользователю {user_id}: {e}")
            fail_count += 1

    return success_count, fail_count
