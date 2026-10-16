"""
==========================================================
FOOD_PORN

Module: Database Models
Layer: Data Access
==========================================================
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now(), nullable=False)


class Language(StrEnum):
    UK = "uk"
    RU = "ru"
    EN = "en"


class ItemCategory(StrEnum):
    MAIN = "main"
    APPETIZER = "appetizer"
    SALAD = "salad"
    SOUP = "soup"
    DESSERT = "dessert"
    DRINK = "drink"


class MenuStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    IMAGES_READY = "images_ready"
    PARTIAL_SUCCESS = "partial_success"
    WAITING_FOR_PAYMENT = "waiting_for_payment"  # Превью готово, ожидается оплата
    PAID = "paid"  # Оплата успешно подтверждена
    SENT_TO_PRINTSHOP = "sent_to_printshop"  # Заказ передан в типографию
    COMPLETED = "completed"
    FAILED = "failed"


class FileKind(StrEnum):
    PREVIEW_OUTSIDE = "preview_outside"
    PREVIEW_INSIDE = "preview_inside"
    PRINT_PDF = "print_pdf"
    PREVIEW = "preview"           # Превью с защитными водяными знаками
    PRODUCTION = "production"     # Чистый PDF для печати
    RECIPE_SHEET = "recipe_sheet" # Пошаговая шпаргалка А4


class GenerationStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    source_channel: Mapped[str] = mapped_column(String(30), default="telegram", nullable=False, index=True)
    external_user_id: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    language: Mapped[Language] = mapped_column(SQLEnum(Language, native_enum=False, length=20), default=Language.UK,
                                               nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    menus: Mapped[list[Menu]] = relationship("Menu", back_populates="customer", cascade="all, delete-orphan")


class Menu(TimestampMixin, Base):
    __tablename__ = "menus"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    cover_photo_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    spread_photo_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Поля для эквайринга и коммерческого цикла
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payment_system: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "portmone" или "redsys"
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    stars_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source_channel: Mapped[str] = mapped_column(String(30), default="telegram", nullable=False, index=True)

    customer: Mapped[Customer] = relationship("Customer", back_populates="menus")
    items: Mapped[list[MenuItem]] = relationship("MenuItem", back_populates="menu", cascade="all, delete-orphan")
    files: Mapped[list[GeneratedFile]] = relationship("GeneratedFile", cascade="all, delete-orphan")


class MenuItem(TimestampMixin, Base):
    __tablename__ = "menu_items"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[ItemCategory] = mapped_column(SQLEnum(ItemCategory, native_enum=False, length=30), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    generation_status: Mapped[GenerationStatus] = mapped_column(SQLEnum(GenerationStatus, native_enum=False, length=30),
                                                                default=GenerationStatus.PENDING, nullable=False)
    image_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    menu: Mapped[Menu] = relationship("Menu", back_populates="items")

    # --- НОВЫЕ ПОЛЯ ДЛЯ ЭМОЦИОНАЛЬНОГО ОПЫТА ---
    menu_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    drink_pairing: Mapped[str | None] = mapped_column(Text, nullable=True)
    romantic_price: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- ХРАНЕНИЕ РЕЦЕПТУРЫ ДЛЯ MINI APP ---
    ingredients: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    recipe: Mapped[str | None] = mapped_column(Text, nullable=True)
    prep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cook_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    servings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(30), nullable=True)
    equipment: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    allergens: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    substitutions: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    shopping_items: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

class GeneratedFile(TimestampMixin, Base):
    __tablename__ = "generated_files"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[FileKind] = mapped_column(SQLEnum(FileKind, native_enum=False, length=30), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = {'extend_existing': True}

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImageCache(TimestampMixin, Base):
    __tablename__ = "image_cache"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)


class WallpaperOrder(TimestampMixin, Base):
    """Persist an invoice, its price and the files already rendered for a customer."""

    __tablename__ = "wallpaper_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    mobile_path: Mapped[str] = mapped_column(Text, nullable=False)
    desktop_path: Mapped[str] = mapped_column(Text, nullable=False)
    paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payment_id: Mapped[str | None] = mapped_column(String(100))
    payment_system: Mapped[str | None] = mapped_column(String(50))
    stars_amount: Mapped[int | None] = mapped_column(Integer)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source_channel: Mapped[str] = mapped_column(String(30), default="telegram", nullable=False, index=True)


class PortmoneSandboxPayment(TimestampMixin, Base):
    """A diagnostic Portmone payment that never grants a digital entitlement."""

    __tablename__ = "portmone_sandbox_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    product: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ShareLink(TimestampMixin, Base):
    __tablename__ = "share_links"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(64), nullable=False)


class EmailDelivery(TimestampMixin, Base):
    __tablename__ = "email_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(254), nullable=False)


class ScheduledDelivery(TimestampMixin, Base):
    __tablename__ = "scheduled_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(254), nullable=False)
    subject: Mapped[str] = mapped_column(String(250), nullable=False)
    attachments: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

class CurrencyRate(TimestampMixin, Base):
    __tablename__ = "currency_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    currency_from: Mapped[str] = mapped_column(String(10), default="USD")
    currency_to: Mapped[str] = mapped_column(String(10), default="UAH")
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)


class AIGenerationLog(TimestampMixin, Base):
    __tablename__ = "ai_generation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    model_name: Mapped[str] = mapped_column(String(100), index=True)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.000000"))
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("41.0000"))
    cost_uah: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"))
    provider: Mapped[str] = mapped_column(String(30), default="openai", nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False, index=True)
    product_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    cached_input_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="success", nullable=False)
    pricing_source: Mapped[str] = mapped_column(String(30), default="estimate", nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ProviderCost(TimestampMixin, Base):
    """An actual provider charge imported from a billing API."""

    __tablename__ = "provider_costs"
    __table_args__ = (UniqueConstraint("external_key", name="uq_provider_costs_external_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    external_key: Mapped[str] = mapped_column(String(64), nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    bucket_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="usd", nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    line_item: Mapped[str | None] = mapped_column(String(150), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ChannelContact(TimestampMixin, Base):
    """A customer identity observed on an external messaging channel."""

    __tablename__ = "channel_contacts"
    __table_args__ = (
        UniqueConstraint("channel", "external_user_id", name="uq_channel_contact_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    external_user_id: Mapped[str] = mapped_column(String(150), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChannelEvent(TimestampMixin, Base):
    """Idempotency journal for incoming messenger webhooks."""

    __tablename__ = "channel_events"
    __table_args__ = (
        UniqueConstraint("channel", "event_id", name="uq_channel_event_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    external_user_id: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
