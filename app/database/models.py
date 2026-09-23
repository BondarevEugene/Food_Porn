"""
==========================================================
FOOD_PORN

Module: Database Models
Layer: Data Access
==========================================================
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import List, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Language(StrEnum):
    UK = "uk"
    RU = "ru"
    EN = "en"


class ItemCategory(StrEnum):
    MAIN = "main"
    APPETIZER = "appetizer"
    SALAD = "salad"      # <-- категгория салаты
    SOUP = "soup"        # <-- категория супы (раз у вас есть борщ и окрошка)
    DESSERT = "dessert"
    DRINK = "drink"


class MenuStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    IMAGES_READY = "images_ready"
    PARTIAL_SUCCESS = "partial_success"
    COMPLETED = "completed"
    FAILED = "failed"


class FileKind(StrEnum):
    PREVIEW_OUTSIDE = "preview_outside"
    PREVIEW_INSIDE = "preview_inside"
    PRINT_PDF = "print_pdf"


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
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    # native_enum=False заставляет SQLAlchemy использовать обычный VARCHAR в базе данных
    language: Mapped[Language] = mapped_column(SQLEnum(Language, native_enum=False, length=20), default=Language.UK, nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    menus: Mapped[List[Menu]] = relationship("Menu", back_populates="customer", cascade="all, delete-orphan")


class Menu(TimestampMixin, Base):
    __tablename__ = "menus"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[MenuStatus] = mapped_column(SQLEnum(MenuStatus, native_enum=False, length=30), default=MenuStatus.DRAFT, nullable=False)
    cover_photo_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    spread_photo_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    customer: Mapped[Customer] = relationship("Customer", back_populates="menus")
    items: Mapped[List[MenuItem]] = relationship("MenuItem", back_populates="menu", cascade="all, delete-orphan")
    files: Mapped[List[GeneratedFile]] = relationship("GeneratedFile", cascade="all, delete-orphan")


class MenuItem(TimestampMixin, Base):
    __tablename__ = "menu_items"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[ItemCategory] = mapped_column(SQLEnum(ItemCategory, native_enum=False, length=30), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    generation_status: Mapped[GenerationStatus] = mapped_column(SQLEnum(GenerationStatus, native_enum=False, length=30), default=GenerationStatus.PENDING, nullable=False)
    image_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generation_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    menu: Mapped[Menu] = relationship("Menu", back_populates="items")


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
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ImageCache(TimestampMixin, Base):
    __tablename__ = "image_cache"
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)