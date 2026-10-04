# src/orchestrator/models.py
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, BigInteger, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column

Base = declarative_base()


class InstanceStatus(str, Enum):
    PENDING = "pending"  # В очереди на создание
    STARTING = "starting"  # Контейнер собирается/запускается
    RUNNING = "running"  # Активен и работает
    STOPPED = "stopped"  # Остановлен (например, кончились деньги)
    FAILED = "failed"  # Упал с ошибкой


class ServiceType(str, Enum):
    TELEGRAM_BOT = "telegram_bot"  # Изолированный runner для aiogram
    WEB_BACKEND = "web_backend"  # FastAPI/Flask инстанс


class ServiceInstance(Base):
    """
    Реестр всех запущенных сервисов на платформе.
    """
    __tablename__ = "service_instances"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(String(255), index=True)

    name: Mapped[str] = mapped_column(String(255))
    service_type: Mapped[ServiceType]

    # Идентификатор физического контейнера в Docker
    container_id: Mapped[str | None] = mapped_column(String(255), unique=True)

    # Хранение специфичных настроек (токены, порты, лимиты CPU/RAM)
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[InstanceStatus] = mapped_column(default=InstanceStatus.PENDING)

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))