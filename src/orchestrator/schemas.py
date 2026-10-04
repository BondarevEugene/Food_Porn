# src/orchestrator/schemas.py
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.orchestrator.models import InstanceStatus, ServiceType


class InstanceCreateRequest(BaseModel):
    name: str = Field(..., example="TinderBolt-v3-Runner")
    service_type: ServiceType
    config: dict[str, Any] = Field(
        ...,
        description="Переменные окружения и настройки (BOT_TOKEN, WEBHOOK_URL и т.д.)"
    )

class InstanceResponse(BaseModel):
    id: int
    name: str
    service_type: ServiceType
    status: InstanceStatus
    created_at: str

    model_config = ConfigDict(from_attributes=True)