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

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
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
    PortmoneSandboxPayment,
    WallpaperExport,
    WallpaperOrder,
    WallpaperSceneVersion,
    WayForPayPayment,
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
            source_channel: str = "telegram",
            external_user_id: str | None = None,
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
                source_channel=source_channel,
                external_user_id=external_user_id,
            )
            self.session.add(customer)
        else:
            customer.telegram_user_id = telegram_user_id
            customer.name = name
            customer.language = language
            customer.country = country
            customer.city = city
            customer.last_seen_at = datetime.now(UTC)
            customer.source_channel = source_channel
            customer.external_user_id = external_user_id
        await self.session.commit()
        await self.session.refresh(customer)
        return customer

    async def touch(self, customer: Customer) -> None:
        customer.last_seen_at = datetime.now(UTC)
        await self.session.commit()


class MenuRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        customer: Customer,
        *,
        source_channel: str | None = None,
        meal_period: str | None = None,
        visual_style: str | None = None,
    ) -> Menu:
        menu = Menu(
            customer_id=customer.id,
            status=MenuStatus.DRAFT,
            source_channel=source_channel or customer.source_channel or "telegram",
            meal_period=meal_period,
            visual_style=visual_style,
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

    async def replace_category_items(
        self,
        *,
        menu_id: int,
        category: ItemCategory,
        titles: list[str],
    ) -> None:
        await self.session.execute(
            delete(MenuItem).where(MenuItem.menu_id == menu_id, MenuItem.category == category)
        )
        self.session.add_all(
            MenuItem(
                menu_id=menu_id,
                category=category,
                position=position,
                title=title,
                generation_status=GenerationStatus.PENDING,
            )
            for position, title in enumerate(titles, start=1)
        )
        await self.session.commit()
        self.session.expire_all()

    async def replace_menu_plan(
        self,
        *,
        menu_id: int,
        entries: list[tuple[str, str, ItemCategory]],
    ) -> None:
        """Replace the complete breakfast/lunch/dinner plan atomically."""
        await self.session.execute(delete(MenuItem).where(MenuItem.menu_id == menu_id))
        self.session.add_all(
            MenuItem(
                menu_id=menu_id,
                meal_slot=meal_slot,
                category=category,
                position=position,
                title=title,
                generation_status=GenerationStatus.PENDING,
            )
            for position, (meal_slot, title, category) in enumerate(entries, start=1)
        )
        await self.session.commit()
        self.session.expire_all()

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

    async def save_recipe_details(self, item: MenuItem, details: dict) -> None:
        """Persist the cooking pack so it survives file cleanup and restarts."""
        item.ingredients = [str(value) for value in details.get("ingredients") or []]
        item.recipe = str(details.get("recipe") or "")
        item.prep_minutes = int(details.get("prep_minutes") or 0)
        item.cook_minutes = int(details.get("cook_minutes") or 0)
        item.servings = int(details.get("servings") or 2)
        item.difficulty = str(details.get("difficulty") or "medium")[:30]
        item.equipment = [str(value) for value in details.get("equipment") or []]
        item.allergens = [str(value) for value in details.get("allergens") or []]
        item.substitutions = [str(value) for value in details.get("substitutions") or []]
        item.shopping_items = [
            value for value in details.get("shopping_items") or [] if isinstance(value, dict)
        ]
        await self.session.commit()

    async def save_file(self, menu_id: int, kind: FileKind | str, path: str) -> GeneratedFile:
        """Безопасное сохранение файла с автоконвертацией типов."""
        if isinstance(kind, str):
            try:
                file_kind_enum = FileKind(kind.lower())
            except ValueError as exc:
                raise ValueError(f"Unsupported file kind: {kind}") from exc
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
            select(Menu).where(Menu.status.in_([MenuStatus.QUEUED, MenuStatus.IMAGES_READY]))
        )
        return list(result.scalars())

    async def set_waiting_for_payment(
        self,
        menu_id: int,
        amount: Decimal,
        stars_amount: int | None = None,
        *,
        payment_id: str | None = None,
        payment_system: str | None = None,
    ) -> None:
        menu = await self.get(menu_id)
        if menu is None:
            raise LookupError(f"Menu {menu_id} not found")
        menu.status = MenuStatus.WAITING_FOR_PAYMENT
        menu.price_amount = amount
        menu.stars_amount = stars_amount
        if payment_id is not None:
            menu.payment_id = payment_id
        if payment_system is not None:
            menu.payment_system = payment_system
        await self.session.commit()

    async def mark_as_paid(self, menu_id: int, payment_id: str, payment_system: str) -> None:
        menu = await self.get(menu_id)
        if menu is None:
            raise LookupError(f"Menu {menu_id} not found")
        menu.is_paid = True
        menu.payment_id = payment_id
        menu.payment_system = payment_system
        menu.paid_at = menu.paid_at or datetime.now(UTC)
        menu.status = MenuStatus.PAID
        await self.session.commit()

    async def mark_sent_to_printshop(self, menu_id: int) -> None:
        menu = await self.get(menu_id)
        if menu is None:
            raise LookupError(f"Menu {menu_id} not found")
        menu.status = MenuStatus.SENT_TO_PRINTSHOP
        await self.session.commit()



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


class WallpaperOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, telegram_user_id: int, amount: Decimal,
                     mobile_path: str, desktop_path: str,
                     stars_amount: int | None = None,
                     source_channel: str = "telegram",
                     goals: list[str] | None = None,
                     scene_prompts: list[str] | None = None,
                     scene_assignments: list[int] | None = None,
                     source_photo_paths: list[str] | None = None,
                     visual_style: str = "dark",
                     raw_mobile_path: str | None = None,
                     raw_desktop_path: str | None = None) -> WallpaperOrder:
        order = WallpaperOrder(
            telegram_user_id=telegram_user_id, amount=amount,
            mobile_path=mobile_path, desktop_path=desktop_path,
            stars_amount=stars_amount,
            source_channel=source_channel,
            goals=goals,
            scene_prompts=scene_prompts,
            scene_assignments=scene_assignments,
            source_photo_paths=source_photo_paths,
            visual_style=visual_style,
            original_mobile_path=mobile_path,
            original_desktop_path=desktop_path,
            raw_mobile_path=raw_mobile_path,
            raw_desktop_path=raw_desktop_path,
        )
        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def get_for_user(self, order_id: int, telegram_user_id: int) -> WallpaperOrder | None:
        result = await self.session.execute(
            select(WallpaperOrder).where(
                WallpaperOrder.id == order_id,
                WallpaperOrder.telegram_user_id == telegram_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def mark_paid(self, order: WallpaperOrder, payment_id: str,
                        payment_system: str = "portmone") -> None:
        order.paid = True
        order.payment_id = payment_id
        order.payment_system = payment_system
        order.paid_at = order.paid_at or datetime.now(UTC)
        await self.session.commit()


class WallpaperStudioRepository:
    """Version and export persistence for the non-destructive scene studio."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def versions(
        self, order_id: int, scene_index: int | None = None
    ) -> list[WallpaperSceneVersion]:
        query = select(WallpaperSceneVersion).where(WallpaperSceneVersion.order_id == order_id)
        if scene_index is not None:
            query = query.where(WallpaperSceneVersion.scene_index == scene_index)
        result = await self.session.execute(
            query.order_by(WallpaperSceneVersion.scene_index, WallpaperSceneVersion.version_number)
        )
        return list(result.scalars().all())

    async def add_version(
        self, *, order_id: int, scene_index: int, scene_asset_path: str,
        edit_mode: str, instruction: str, ai_cost_usd: Decimal,
    ) -> WallpaperSceneVersion:
        latest = await self.session.scalar(
            select(func.max(WallpaperSceneVersion.version_number)).where(
                WallpaperSceneVersion.order_id == order_id,
                WallpaperSceneVersion.scene_index == scene_index,
            )
        )
        version = WallpaperSceneVersion(
            order_id=order_id,
            scene_index=scene_index,
            version_number=int(latest or 0) + 1,
            scene_asset_path=scene_asset_path,
            edit_mode=edit_mode,
            instruction=instruction,
            ai_cost_usd=ai_cost_usd,
        )
        self.session.add(version)
        await self.session.commit()
        await self.session.refresh(version)
        return version

    async def get_version(self, version_id: int, order_id: int) -> WallpaperSceneVersion | None:
        return await self.session.scalar(
            select(WallpaperSceneVersion).where(
                WallpaperSceneVersion.id == version_id,
                WallpaperSceneVersion.order_id == order_id,
            )
        )

    async def select_version(self, order: WallpaperOrder, version: WallpaperSceneVersion) -> None:
        selected = await self.versions(order.id, version.scene_index)
        for item in selected:
            item.is_selected = item.id == version.id
        await self.session.commit()

    async def save_export(
        self, *, order_id: int, kind: str, path: str, mime_type: str,
        source_revision: str, width: int | None = None, height: int | None = None,
        duration_seconds: Decimal | None = None,
    ) -> WallpaperExport:
        record = await self.session.scalar(
            select(WallpaperExport).where(
                WallpaperExport.order_id == order_id, WallpaperExport.kind == kind
            )
        )
        if record is None:
            record = WallpaperExport(
                order_id=order_id, kind=kind, path=path,
                mime_type=mime_type, source_revision=source_revision,
            )
            self.session.add(record)
        record.path = path
        record.mime_type = mime_type
        record.source_revision = source_revision
        record.width = width
        record.height = height
        record.duration_seconds = duration_seconds
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def exports(self, order_id: int) -> list[WallpaperExport]:
        result = await self.session.execute(
            select(WallpaperExport).where(WallpaperExport.order_id == order_id).order_by(
                WallpaperExport.kind
            )
        )
        return list(result.scalars().all())


class PortmoneSandboxPaymentRepository:
    """Persist isolated test payments without changing product payment status."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        telegram_user_id: int,
        product: str,
        reference_id: str,
        amount: Decimal,
    ) -> PortmoneSandboxPayment:
        if product not in {"menu", "wallpaper"}:
            raise ValueError("Unsupported sandbox product")
        payment = PortmoneSandboxPayment(
            telegram_user_id=telegram_user_id,
            product=product,
            reference_id=reference_id,
            amount=amount,
        )
        self.session.add(payment)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def get_for_user(
        self, payment_id: int, telegram_user_id: int
    ) -> PortmoneSandboxPayment | None:
        result = await self.session.execute(
            select(PortmoneSandboxPayment).where(
                PortmoneSandboxPayment.id == payment_id,
                PortmoneSandboxPayment.telegram_user_id == telegram_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def mark_paid(self, payment: PortmoneSandboxPayment, provider_payment_id: str) -> None:
        payment.status = "paid"
        payment.payment_id = provider_payment_id
        payment.error_message = None
        await self.session.commit()

    async def mark_failed(self, payment: PortmoneSandboxPayment, reason: str) -> None:
        payment.status = "failed"
        payment.error_message = reason[:1000]
        await self.session.commit()


class WayForPayPaymentRepository:
    """Store checkout attempts separately from product entitlement records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        telegram_user_id: int,
        product: str,
        reference_id: str,
        order_reference: str,
        checkout_token: str,
        amount: Decimal,
        description: str,
        test_mode: bool,
        grants_entitlement: bool,
    ) -> WayForPayPayment:
        if product not in {"menu", "wallpaper"}:
            raise ValueError("Unsupported WayForPay product")
        payment = WayForPayPayment(
            telegram_user_id=telegram_user_id,
            product=product,
            reference_id=str(reference_id),
            order_reference=order_reference,
            checkout_token=checkout_token,
            amount=amount,
            currency="UAH",
            description=description[:250],
            test_mode=test_mode,
            grants_entitlement=grants_entitlement,
        )
        self.session.add(payment)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def by_checkout_token(self, token: str) -> WayForPayPayment | None:
        result = await self.session.execute(
            select(WayForPayPayment).where(WayForPayPayment.checkout_token == token)
        )
        return result.scalar_one_or_none()

    async def get_for_user(
        self, payment_id: int, telegram_user_id: int
    ) -> WayForPayPayment | None:
        result = await self.session.execute(
            select(WayForPayPayment).where(
                WayForPayPayment.id == payment_id,
                WayForPayPayment.telegram_user_id == telegram_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def by_order_reference(
        self, order_reference: str, *, lock: bool = False
    ) -> WayForPayPayment | None:
        query = select(WayForPayPayment).where(
            WayForPayPayment.order_reference == order_reference
        )
        if lock:
            query = query.with_for_update()
        return (await self.session.execute(query)).scalar_one_or_none()

    async def latest_for_product(
        self, product: str, reference_id: str, telegram_user_id: int
    ) -> WayForPayPayment | None:
        result = await self.session.execute(
            select(WayForPayPayment)
            .where(
                WayForPayPayment.product == product,
                WayForPayPayment.reference_id == str(reference_id),
                WayForPayPayment.telegram_user_id == telegram_user_id,
            )
            .order_by(WayForPayPayment.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
