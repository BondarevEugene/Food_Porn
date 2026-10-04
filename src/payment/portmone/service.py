# src/payment/portmone/service.py
import hashlib
import urllib.parse
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.billing.service import BillingService
from src.payment.portmone.config import portmone_settings
from src.payment.portmone.schemas import PortmoneWebhookPayload


class PortmoneService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.billing = BillingService(db_session)

    def _generate_signature(self, **kwargs) -> str:
        """
        Генерация подписи для верификации запросов.
        Формируется конкатенацией параметров и хешированием (обычно MD5/SHA256)
        вместе с секретным ключом мерчанта.
        """
        # Порядок ключей должен строго соответствовать документации Portmone
        raw_string = f"{kwargs.get('shop_order_number', '')}{portmone_settings.secret_key}"
        return hashlib.md5(raw_string.encode('utf-8')).hexdigest().upper()

    def _verify_webhook_signature(self, payload: PortmoneWebhookPayload) -> bool:
        """Проверяет подлинность запроса от серверов Portmone."""
        expected_signature = self._generate_signature(
            shop_order_number=payload.shop_order_number,
            status=payload.status,
            bill_amount=payload.bill_amount
        )
        return expected_signature == payload.signature

    async def create_payment_url(self, owner_id: str, amount_cents: int) -> tuple[str, str]:
        """
        Генерирует уникальный номер заказа и формирует GET/POST ссылку
        для перенаправления пользователя на эквайринг.
        """
        order_id = f"ORDER-{uuid.uuid4().hex[:12].upper()}"
        amount_uah = amount_cents / 100.0

        # В реальной системе перед выдачей ссылки стоит создать в БД транзакцию со статусом PENDING

        params = {
            "payee_id": portmone_settings.payee_id,
            "shop_order_number": order_id,
            "bill_amount": f"{amount_uah:.2f}",
            "description": f"Пополнение баланса аккаунта {owner_id}",
            "success_url": portmone_settings.success_url,
            "failure_url": portmone_settings.failure_url,
            "encoding": "UTF-8",
        }

        # Для Gateway часто используется отправка пользователя на URL с GET параметрами
        query_string = urllib.parse.urlencode(params)
        payment_url = f"{portmone_settings.gateway_url}?{query_string}"

        return payment_url, order_id

    async def process_webhook(self, payload: PortmoneWebhookPayload):
        """
        Обработка асинхронного уведомления от Portmone.
        Это критический участок: здесь реальные деньги зачисляются на баланс.
        """
        if not self._verify_webhook_signature(payload):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature"
            )

        if payload.status != "PAYED":
            # Логируем отказ, но баланс не меняем
            return {"status": "ignored", "reason": "Payment not successful"}

        # Извлекаем ID пользователя из нашей базы по номеру заказа (shop_order_number)
        # В реальном коде нужен запрос к БД для поиска owner_id по order_id
        owner_id = self._extract_owner_from_order(payload.shop_order_number)

        # Переводим сумму обратно в минимальные единицы (копейки)
        amount_cents = int(payload.bill_amount * 100)

        # Вызываем ядро биллинга для зачисления средств
        # Зачисление происходит с блокировкой строки (FOR UPDATE), чтобы избежать двойного начисления
        await self.billing.deposit_funds(
            owner_id=owner_id,
            amount=amount_cents,
            reference_id=payload.shop_order_number,
            description="Пополнение через Portmone"
        )

        return {"status": "success"}

    def _extract_owner_from_order(self, order_id: str) -> str:
        # Заглушка: здесь должен быть SELECT к таблице ордеров или извлечение метаданных
        return "user_123"
