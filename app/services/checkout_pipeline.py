"""
==========================================================
FOOD_PORN

Module: Checkout & Queue Pipeline Integration
Layer: Services / Workers
Responsibilities:
    - Проверка статуса платежа через PaymentService (Portmone)
    - Безопасный запуск генерации через QueueManager после верификации
==========================================================
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.payment import PaymentError, PaymentService
from app.workers.queue import QueueManager  # Предполагается наличие нашего воркера очередей

logger = logging.getLogger(__name__)


class CheckoutPipelineService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.payment_service = PaymentService(settings)

    async def verify_and_dispatch(
            self,
            menu_id: int,
            expected_amount: float,
            generation_task_func,
            *args,
            **kwargs
    ) -> bool:
        """
        Проверяет реальное поступление средств через Portmone и,
        если оплата подтверждена, ставит задачу генерации в очередь.
        """
        try:
            # 1. Серверная верификация платежа по стандартам Portmone API
            verified_payment = await self.payment_service.verify_portmone_payment(
                menu_id=menu_id,
                expected_amount=expected_amount,
                product="menu"
            )

            if not verified_payment:
                logger.warning(f"Платеж для меню {menu_id} еще не подтвержден шлюзом.")
                return False

            logger.info(
                f"Платеж верифицирован! ID транзакции: {verified_payment.payment_id}, "
                f"сумма: {verified_payment.amount} UAH"
            )

            # 2. Передаем задачу на генерацию в защищенную очередь с concurrency=1
            await QueueManager.schedule_generation(
                generation_task_func,
                *args,
                **kwargs
            )

            return True

        except PaymentError as exc:
            logger.error(f"Ошибка проверки платежа Portmone для меню {menu_id}: {exc}")
            return False
        except Exception as exc:
            logger.critical(f"Непредвиденный сбой в пайплайне оплаты и очереди: {exc}")
            raise exc