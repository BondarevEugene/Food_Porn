"""
==========================================================
FOOD_PORN

Module: Database Repositories
Layer: Persistence

Responsibilities:
    - Encapsulate customer, menu, item, and cache queries
    - Persist workflow and generation status changes
    - Keep SQLAlchemy operations out of Telegram handlers
    - Robust normalization and enterprise-grade error handling
==========================================================
"""

from datetime import UTC, datetime
import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import (
    Customer,
    FileKind,
    GeneratedFile,
    GenerationStatus,
    ImageCache,
    ItemCategory,
    Language,
    Menu,
    MenuItem,
    MenuStatus,
)

logger = logging.getLogger(__name__)

SKIP_WORDS = frozenset({"пас", "pass", "skip", "пропустить"})


def is_skipped_title(title: str) -> bool:
    return title.strip().casefold() in SKIP_WORDS


class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def by_telegram_id(self, telegram_user_id: int) -> Customer | None:
        result = await self.session.execute(
            select(Customer).where(Customer.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def by_phone(self, phone: str) -> Customer | None:
        result = await self.session.execute(select(Customer).where(Customer.phone == phone))
        return result.scalar_one_or_none()

    async def register(
        self,
        *,
        telegram_user_id: int,
        phone: str,
        name: str,
        language: Language,
        country: str,
        city: str,
    ) -> Customer:
        customer = await self.by_phone(phone)
        if customer is None:
            customer = Customer(
                telegram_user_id=telegram_user_id,
                phone=phone,
                name=name,
                language=language,
                country=country,
                city=city,
            )
            self.session.add(customer)
        else:
            customer.telegram_user_id = telegram_user_id
            customer.name = name
            customer.language = language
            customer.country = country
            customer.city = city
            customer.last_seen_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(customer)
        return customer

    async def touch(self, customer: Customer) -> None:
        customer.last_seen_at = datetime.now(UTC)
        await self.session.commit()


class MenuRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, customer: Customer) -> Menu:
        menu = Menu(
            customer_id=customer.id,
            status=MenuStatus.DRAFT,
        )
        self.session.add(menu)
        await self.session.commit()
        await self.session.refresh(menu)
        return menu

    async def get(self, menu_id: int, *, full: bool = False) -> Menu | None:
        statement = select(Menu).where(Menu.id == menu_id)
        if full:
            statement = statement.options(
                selectinload(Menu.customer), selectinload(Menu.items), selectinload(Menu.files)
            )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def add_item(
        self,
        *,
        menu_id: int,
        category: ItemCategory | str,
        position: int,
        title: str,
    ) -> MenuItem:
        """Добавляет блюдо в меню с защитой от несоответствия регистра Enum."""
        normalized_title = title.strip()
        skipped = is_skipped_title(normalized_title)

        # Превращаем категорию в корректный Enum или нижний регистр для БД
        if isinstance(category, str):
            try:
                cat_enum = ItemCategory(category.lower())
            except ValueError:
                cat_enum = ItemCategory.MAIN
        else:
            cat_enum = category

        item = MenuItem(
            menu_id=menu_id,
            category=cat_enum,
            position=position,
            title="—" if skipped else normalized_title,
            generation_status=GenerationStatus.DONE if skipped else GenerationStatus.PENDING,
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def reset_items(self, menu_id: int) -> None:
        await self.session.execute(delete(MenuItem).where(MenuItem.menu_id == menu_id))
        await self.session.commit()

    async def set_photos(self, menu_id: int, *, cover: str | None = None, spread: str | None = None) -> None:
        menu = await self.get(menu_id)
        if menu is None:
            raise LookupError(f"Menu {menu_id} not found")
        if cover is not None:
            menu.cover_photo_path = cover
        if spread is not None:
            menu.spread_photo_path = spread
        await self.session.commit()

    async def set_status(
        self, menu_id: int, status: MenuStatus, error_message: str | None = None
    ) -> None:
        menu = await self.get(menu_id)
        if menu is None:
            raise LookupError(f"Menu {menu_id} not found")
        menu.status = status
        menu.error_message = error_message
        await self.session.commit()

    async def set_item_processing(self, item: MenuItem, prompt: str) -> None:
        item.image_prompt = prompt
        item.generation_status = GenerationStatus.PROCESSING
        item.generation_error = None
        await self.session.commit()

    async def set_item_done(self, item: MenuItem, path: str) -> None:
        item.image_path = path
        item.generation_status = GenerationStatus.DONE
        item.generation_error = None
        await self.session.commit()

    async def set_item_failed(self, item: MenuItem, error: str) -> None:
        item.generation_status = GenerationStatus.FAILED
        item.generation_error = error[:2000]
        await self.session.commit()

    async def save_file(self, menu_id: int, kind: FileKind | str, path: str) -> GeneratedFile:
        """Безопасное сохранение файла с автоконвертацией типов."""
        if isinstance(kind, str):
            try:
                file_kind_enum = FileKind(kind.lower())
            except ValueError:
                file_kind_enum = FileKind.PDF
        else:
            file_kind_enum = kind

        result = await self.session.execute(
            select(GeneratedFile).where(
                GeneratedFile.menu_id == menu_id, GeneratedFile.kind == file_kind_enum
            )
        )
        generated = result.scalar_one_or_none()
        if generated is None:
            generated = GeneratedFile(menu_id=menu_id, kind=file_kind_enum, path=path)
            self.session.add(generated)
        else:
            generated.path = path
        await self.session.commit()
        await self.session.refresh(generated)
        return generated

    async def recent_for_customer(self, customer_id: int, limit: int = 5) -> list[Menu]:
        result = await self.session.execute(
            select(Menu)
            .where(Menu.customer_id == customer_id)
            .order_by(Menu.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def resumable(self) -> list[Menu]:
        result = await self.session.execute(
            select(Menu).where(Menu.status.in_([MenuStatus.QUEUED, MenuStatus.GENERATING]))
        )
        return list(result.scalars())


class ImageCacheRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, cache_key: str) -> ImageCache | None:
        result = await self.session.execute(
            select(ImageCache).where(ImageCache.cache_key == cache_key)
        )
        return result.scalar_one_or_none()

    async def put(self, *, cache_key: str, model: str, prompt: str, path: str) -> ImageCache:
        existing = await self.get(cache_key)
        if existing is not None:
            existing.path = path
            await self.session.commit()
            return existing
        record = ImageCache(cache_key=cache_key, model=model, prompt=prompt, path=path)
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record
