# src/billing/router.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.billing.exceptions import InsufficientFundsError
from src.billing.schemas import AccountResponse
from src.billing.service import BillingService

from aiogram import Bot
from app.config import settings  # или ваш импорт конфигурации бота

# Предполагается наличие зависимости для получения сессии БД
# from src.database.dependencies import get_db_session

router = APIRouter(prefix="/api/v1/billing", tags=["Billing"])


@router.get("/accounts/{owner_id}", response_model=AccountResponse)
async def get_account_info(owner_id: str, db: AsyncSession = Depends(get_db_session)):
    service = BillingService(db)
    return await service.get_account(owner_id)


@router.post("/execute-paid-action")
async def execute_paid_action(owner_id: str, db: AsyncSession = Depends(get_db_session)):
    """
    Пример интеграционного эндпоинта.
    Демонстрирует паттерн "Резервирование -> Исполнение -> Списание/Возврат"
    """
    service = BillingService(db)
    cost = 100  # Стоимость генерации в условных единицах
    req_id = str(uuid.uuid4())

    # 1. Пытаемся заморозить средства
    try:
        await service.reserve_funds(owner_id, amount=cost, reference_id=req_id)
    except InsufficientFundsError as e:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e))

    # 2. Имитация вызова внешнего API (OpenAI / Replicate)
    try:
        # result = await openai_client.generate_image(...)
        api_success = True
    except Exception:
        api_success = False

    # 3. Финализация транзакции
    if api_success:
        await service.commit_hold(owner_id, cost, req_id)
        return {"status": "success", "message": "Контент сгенерирован, средства списаны."}
    else:
        # Если OpenAI упал, деньги возвращаются клиенту мгновенно
        await service.rollback_hold(owner_id, cost, req_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Внешний сервис недоступен. Средства возвращены на баланс."
        )
