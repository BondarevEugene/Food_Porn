# src/billing/schemas.py
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.billing.models import TransactionType


class AccountResponse(BaseModel):
    id: int
    owner_id: str
    available_balance: int = Field(description="Доступные для трат средства")
    held_balance: int = Field(description="Замороженные средства (в процессе транзакции)")

    model_config = ConfigDict(from_attributes=True)


class HoldRequest(BaseModel):
    amount: int = Field(gt=0, description="Сумма для блокировки")
    reference_id: str = Field(..., description="ID запроса к нейросети или ID сессии")
    description: str | None = None


class TransactionResponse(BaseModel):
    id: int
    amount: int
    type: TransactionType
    reference_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)