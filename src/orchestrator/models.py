
"""Database models for infrastructure orchestration."""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON, BigInteger, String
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

Base = declarative_base()


class InstanceStatus(StrEnum):
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class ServiceType(StrEnum):
    TELEGRAM_BOT = "telegram_bot"
    WEB_BACKEND = "web_backend"


class ServiceInstance(Base):
    """Registry of service instances deployed on the platform."""

    __tablename__ = "service_instances"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    owner_id: Mapped[str] = mapped_column(String(255), index=True)

    name: Mapped[str] = mapped_column(String(255))
    service_type: Mapped[ServiceType]

    container_id: Mapped[str | None] = mapped_column(
        String(255), unique=True
    )

    config: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[InstanceStatus] = mapped_column(
        default=InstanceStatus.PENDING
    )

    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
