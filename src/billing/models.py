"""
==========================================================
FOOD_PORN & OLD MONEY • ENTERPRISE DATA MODELS
==========================================================
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum, StrEnum
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

Base = declarative_base()


# --- ФИНАНСОВЫЕ ЕНАУМЫ И МОДЕЛИ (LEDGER & BILLING) ---

class TransactionType(str, Enum):
    DEPOSIT = "deposit"  # Пополнение баланса
    HOLD = "hold"  # Блокировка средств под выполнение API-запроса
    COMMIT = "commit"  # Списание ранее заблокированных средств
    REFUND = "refund"  # Возврат (отмена HOLD)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    available_balance: Mapped[int] = mapped_column(BigInteger, default=0)
    held_balance: Mapped[int] = mapped_column(BigInteger, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")

    __table_args__ = (
        CheckConstraint('available_balance >= 0', name='check_positive_available'),
        CheckConstraint('held_balance >= 0', name='check_positive_held'),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)

    amount: Mapped[int] = mapped_column(BigInteger)
    type: Mapped[TransactionType] = mapped_column(SQLEnum(TransactionType, native_enum=False, length=20))

    reference_id: Mapped[str | None] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())

    account: Mapped["Account"] = relationship(back_populates="transactions")


class ProductPrice(Base):
    """Динамические цены продуктов с привязкой к дате активации (effective_from)."""
    __tablename__ = "product_prices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_key: Mapped[str] = mapped_column(String(100), index=True, default="collage_uah")
    price_value: Mapped[float] = mapped_column(Float, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --- ОСНОВНЫЕ МОДЕЛИ БОТА И CRM (CUSTOMERS & MENUS) ---

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now(), nullable=False)


class Language(StrEnum):
    UK = "uk"
    RU = "ru"
    EN = "en"


class MenuStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    IMAGES_READY = "images_ready"
    WAITING_FOR_PAYMENT = "waiting_for_payment"
    PAID = "PAID"
    CANCELED = "CANCELED"
    SENT_TO_PRINTSHOP = "sent_to_printshop"
    COMPLETED = "completed"
    FAILED = "failed"


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    language: Mapped[Language] = mapped_column(SQLEnum(Language, native_enum=False, length=20), default=Language.UK,
                                               nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Реферальное поле
    referred_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    menus: Mapped[list[Menu]] = relationship("Menu", back_populates="customer", cascade="all, delete-orphan")


class Menu(TimestampMixin, Base):
    __tablename__ = "menus"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[MenuStatus] = mapped_column(SQLEnum(MenuStatus, native_enum=False, length=30),
                                               default=MenuStatus.DRAFT, nullable=False)

    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payment_system: Mapped[str | None] = mapped_column(String(50), nullable=True)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    customer: Mapped[Customer] = relationship("Customer", back_populates="menus")


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = {'extend_existing': True}

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
