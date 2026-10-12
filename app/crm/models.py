"""Additive CRM tables, separate from the bot's legacy metadata."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CRMBase(DeclarativeBase):
    pass


class Expense(CRMBase):
    __tablename__ = "crm_expenses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    category: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(String(500))
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    created_by: Mapped[str] = mapped_column(String(100))
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    voided: Mapped[bool] = mapped_column(Boolean, default=False)
    void_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class Audit(CRMBase):
    __tablename__ = "crm_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor: Mapped[str] = mapped_column(String(100), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class Integration(CRMBase):
    __tablename__ = "crm_integrations"
    provider: Mapped[str] = mapped_column(String(30), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    encrypted_secrets: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="not_configured")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    report: Mapped[dict | None] = mapped_column(JSON)


class CustomerNote(CRMBase):
    __tablename__ = "crm_customer_notes"
    telegram_user_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    note: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[str] = mapped_column(String(100))


async def initialize_schema(engine) -> None:
    # Only these four tables are created. Existing bot tables and Alembic head
    # are never altered, avoiding the differing local migration chains.
    async with engine.begin() as connection:
        await connection.run_sync(CRMBase.metadata.create_all)
