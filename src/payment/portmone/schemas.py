# src/payment/portmone/schemas.py
from pydantic import BaseModel, Field


class PortmonePaymentLinkRequest(BaseModel):
    """Данные, которые передает наш фронтенд или бот для генерации ссылки."""
    owner_id: str = Field(..., description="ID пользователя в нашей системе (Telegram ID)")
    amount: int = Field(..., gt=0, description="Сумма пополнения в копейках")
    currency: str = Field(default="UAH")

class PortmonePaymentLinkResponse(BaseModel):
    """Ответ для клиента с готовой ссылкой на оплату."""
    payment_url: str
    order_id: str

class PortmoneWebhookPayload(BaseModel):
    """
    Структура данных, приходящая от Portmone (Result URL / Callback).
    Названия полей строго соответствуют документации шлюза.
    """
    shop_order_number: str
    bill_amount: float
    description: str | None = None
    status: str = Field(..., description="PAYED, REJECTED и т.д.")
    error_code: str | None = None
    error_message: str | None = None
    # Подпись (signature) обычно передается либо в теле, либо в заголовках
    signature: str
