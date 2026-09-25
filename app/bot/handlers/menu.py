"""
==========================================================
FOOD_PORN

Module: Menu Workflow Handlers (Enterprise Dashboard)
Layer: Telegram Interface

Responsibilities:
    - Premium interactive dashboard for menu management
    - Dynamic dish addition with real-time database persistence
    - Seamless photo uploads (cover, spread)
    - Integration with background processing pipeline and user history
==========================================================
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.helpers import current_customer
from app.config import Settings
from app.database.models import ItemCategory, Menu, MenuStatus
from app.database.repositories import MenuRepository
from app.services.storage import InvalidImageError, StorageService
from app.workers.menu_pipeline import MenuPipeline

logger = logging.getLogger(__name__)
router = Router(name="menu")


class PremiumMenuStates(StatesGroup):
    waiting_for_dish_name = State()
    waiting_for_cover = State()
    waiting_for_spread = State()


class MenuAction(CallbackData, prefix="menu"):
    action: str
    menu_id: int
    category: str | None = None


def format_premium_dashboard(menu: Menu) -> str:
    """Формирует премиальный текстовый интерфейс дашборда на основе реальных данных БД."""
    status_icon = "⚫️" if menu.status == MenuStatus.DRAFT else "⚜️"
    status_text = "Формирование" if menu.status == MenuStatus.DRAFT else str(menu.status).capitalize()

    lines = [
        f"⚜️ <b>Гастрономический сет #{menu.id}</b>",
        f"Статус: {status_icon} <i>{status_text}</i>",
        ""
    ]

    cover_status = "✅ Загружена" if menu.cover_photo_path else "❌ Отсутствует"
    spread_status = "✅ Загружен" if menu.spread_photo_path else "❌ Отсутствует"
    lines.append(f"🖼 Обложка: {cover_status}")
    lines.append(f"📔 Разворот: {spread_status}")
    lines.append("")

    if not menu.items:
        lines.append("<i>Сет пока пуст. Добавьте позиции для начала работы.</i>")
    else:
        lines.append("<b>Утвержденные подачи:</b>")
        icons = {
            ItemCategory.MAIN: "🍽",
            ItemCategory.APPETIZER: "🥢",
            ItemCategory.SALAD: "🥗",
            ItemCategory.SOUP: "🥣",
            ItemCategory.DESSERT: "🍰",
            ItemCategory.DRINK: "🍷"
        }
        for idx, item in enumerate(menu.items, start=1):
            icon = icons.get(item.category, "▪️")
            lines.append(f"  {idx}. {icon} {item.title}")

    lines.extend([
        "",
        "<i>Нейросеть автоматически подберет рецептуру, сформирует</i>",
        "<i>консолидированный лист закупок и стилизует иллюстрации.</i>"
    ])

    return "\n".join(lines)


def build_dashboard_kb(menu: Menu) -> InlineKeyboardMarkup:
    """Генерирует инлайн-клавиатуру для управления сетом."""
    builder = InlineKeyboardBuilder()

    builder.button(
        text="➕ Добавить блюдо",
        callback_data=MenuAction(action="pick_category", menu_id=menu.id)
    )
    if menu.items:
        builder.button(
            text="🗑 Очистить блюда",
            callback_data=MenuAction(action="clear_items", menu_id=menu.id)
        )

    builder.button(
        text="🖼 Обложка",
        callback_data=MenuAction(action="req_cover", menu_id=menu.id)
    )
    builder.button(
        text="📔 Разворот",
        callback_data=MenuAction(action="req_spread", menu_id=menu.id)
    )

    can_generate = bool(menu.items and menu.cover_photo_path and menu.spread_photo_path)

    # Разрешаем запуск для DRAFT, FAILED, а также QUEUED (на случай зависших сетов)
    if menu.status in (MenuStatus.DRAFT, MenuStatus.FAILED, MenuStatus.QUEUED):
        if can_generate:
            builder.button(
                text="⚫️ Утвердить и сгенерировать",
                callback_data=MenuAction(action="generate", menu_id=menu.id)
            )
        else:
            builder.button(
                text="⚠️ Заполните данные для генерации",
                callback_data="ignore"
            )

    builder.adjust(2, 2, 1)
    return builder.as_markup()


def build_category_kb(menu_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора категории нового блюда."""
    builder = InlineKeyboardBuilder()
    categories = [
        ("Основное блюдо", ItemCategory.MAIN),
        ("Закуска", ItemCategory.APPETIZER),
        ("Салат", ItemCategory.SALAD),
        ("Суп", ItemCategory.SOUP),
        ("Десерт", ItemCategory.DESSERT),
        ("Напиток", ItemCategory.DRINK),
    ]
    for text, cat in categories:
        builder.button(text=text, callback_data=MenuAction(action="add_item", menu_id=menu_id, category=cat.value))

    builder.button(text="🔙 Назад к сету", callback_data=MenuAction(action="view", menu_id=menu_id))
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


@router.message(Command("new"))
async def create_new_menu(
        message: Message,
        state: FSMContext,
        session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Создает новый черновик меню и выводит дашборд."""
    await state.clear()

    async with session_factory() as session:
        customer = await current_customer(session, message.from_user.id)
        if not customer:
            await message.answer("Сначала зарегистрируйтесь командой /start.")
            return

        repo = MenuRepository(session)
        new_menu = await repo.create(customer)
        menu = await repo.get(new_menu.id, full=True)

        text = format_premium_dashboard(menu)
        kb = build_dashboard_kb(menu)

    msg = await message.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.update_data(dashboard_message_id=msg.message_id, menu_id=menu.id)


@router.callback_query(MenuAction.filter(F.action == "view"))
async def view_dashboard(
    callback: CallbackQuery,
    callback_data: MenuAction,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await state.set_state(None)
    async with session_factory() as session:
        menu = await MenuRepository(session).get(callback_data.menu_id, full=True)

    if not menu:
        await callback.answer("Сет не найден.", show_alert=True)
        return

    await callback.message.edit_text(
        format_premium_dashboard(menu),
        reply_markup=build_dashboard_kb(menu),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(MenuAction.filter(F.action == "pick_category"))
async def pick_item_category(callback: CallbackQuery, callback_data: MenuAction) -> None:
    await callback.message.edit_text(
        "<b>Выберите категорию подачи:</b>\n<i>От этого зависит визуальный стиль иллюстрации.</i>",
        reply_markup=build_category_kb(callback_data.menu_id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(MenuAction.filter(F.action == "add_item"))
async def prompt_item_name(
    callback: CallbackQuery,
    callback_data: MenuAction,
    state: FSMContext
) -> None:
    await state.set_state(PremiumMenuStates.waiting_for_dish_name)
    await state.update_data(
        menu_id=callback_data.menu_id,
        category=callback_data.category
    )

    await callback.message.edit_text(
        "🖋 <b>Введите название блюда:</b>\n<i>Например: Медальоны из телятины с трюфельным соусом</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(PremiumMenuStates.waiting_for_dish_name, F.text)
async def receive_dish_name(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    title = message.text.strip()
    data = await state.get_data()
    menu_id = data.get("menu_id")
    category_val = data.get("category")

    if not 2 <= len(title) <= 180:
        await message.answer("⚠️ Название должно быть от 2 до 180 символов.")
        return

    async with session_factory() as session:
        repo = MenuRepository(session)
        menu = await repo.get(menu_id, full=True)
        if not menu:
            return

        position = len(menu.items) + 1

        await repo.add_item(
            menu_id=menu_id,
            category=ItemCategory(category_val),
            position=position,
            title=title
        )

        menu = await repo.get(menu_id, full=True)

    await state.set_state(None)

    msg = await message.answer(
        format_premium_dashboard(menu),
        reply_markup=build_dashboard_kb(menu),
        parse_mode="HTML"
    )
    await state.update_data(dashboard_message_id=msg.message_id)


@router.callback_query(MenuAction.filter(F.action == "clear_items"))
async def clear_items(
    callback: CallbackQuery,
    callback_data: MenuAction,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        repo = MenuRepository(session)
        await repo.reset_items(callback_data.menu_id)
        menu = await repo.get(callback_data.menu_id, full=True)

    await callback.message.edit_text(
        format_premium_dashboard(menu),
        reply_markup=build_dashboard_kb(menu),
        parse_mode="HTML"
    )
    await callback.answer("Блюда удалены")


@router.callback_query(MenuAction.filter(F.action.in_(["req_cover", "req_spread"])))
async def prompt_photo(callback: CallbackQuery, callback_data: MenuAction, state: FSMContext) -> None:
    is_cover = callback_data.action == "req_cover"
    target_state = PremiumMenuStates.waiting_for_cover if is_cover else PremiumMenuStates.waiting_for_spread
    role_name = "обложки" if is_cover else "разворота"

    await state.set_state(target_state)
    await state.update_data(menu_id=callback_data.menu_id)

    await callback.message.edit_text(
        f"🖼 <b>Отправьте фотографию для {role_name}:</b>\n<i>Файл должен быть изображением (не файлом/документом).</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(PremiumMenuStates.waiting_for_cover, F.photo)
@router.message(PremiumMenuStates.waiting_for_spread, F.photo)
async def receive_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    menu_id = data.get("menu_id")
    current_state = await state.get_state()
    role = "cover" if current_state == PremiumMenuStates.waiting_for_cover.state else "spread"

    try:
        path = await StorageService(settings).save_telegram_photo(
            bot, message.photo[-1].file_id, menu_id=menu_id, role=role
        )
    except InvalidImageError:
        await message.answer(f"⚠️ Ошибка формата. Загрузите корректное фото (до {settings.max_upload_mb} MB).")
        return

    async with session_factory() as session:
        repo = MenuRepository(session)
        kwargs = {"cover": str(path)} if role == "cover" else {"spread": str(path)}
        await repo.set_photos(menu_id, **kwargs)
        menu = await repo.get(menu_id, full=True)

    await state.set_state(None)
    msg = await message.answer(
        format_premium_dashboard(menu),
        reply_markup=build_dashboard_kb(menu),
        parse_mode="HTML"
    )
    await state.update_data(dashboard_message_id=msg.message_id)


@router.message(PremiumMenuStates.waiting_for_cover)
@router.message(PremiumMenuStates.waiting_for_spread)
async def photo_invalid_format(message: Message, settings: Settings) -> None:
    await message.answer(f"⚠️ Пожалуйста, отправьте сжатое фото (до {settings.max_upload_mb} MB).")


@router.callback_query(MenuAction.filter(F.action == "generate"))
async def confirm_generation(
        callback: CallbackQuery, callback_data: MenuAction,
        state: FSMContext, session_factory: async_sessionmaker[AsyncSession],
        pipeline: MenuPipeline,
) -> None:
    async with session_factory() as session:
        repo = MenuRepository(session)
        menu = await repo.get(callback_data.menu_id, full=True)

        # Разрешаем запуск для Draft, Failed, а также зависших Queued сетов
        if not menu or menu.status == MenuStatus.COMPLETED:
            await callback.answer("Сет уже успешно завершен.", show_alert=True)
            return

        await repo.set_status(menu.id, MenuStatus.QUEUED)

    await callback.message.edit_text(
        f"⚜️ <b>Гастрономический сет #{menu.id}</b>\n"
        f"Статус: 🟡 <i>Утвержден, отправлен в нейросети</i>\n\n"
        f"<i>Алгоритмы генерируют рецепты и консолидируют лист закупок.\nОжидайте готовый PDF-документ.</i>",
        parse_mode="HTML"
    )

    await pipeline.submit(menu.id, callback.from_user.id)
    await state.clear()
    await callback.answer("Отправлено в обработку")


@router.message(Command("history"))
async def history_command(
        message: Message,
        session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        customer = await current_customer(session, message.from_user.id)
        if not customer:
            return

        menus = await MenuRepository(session).recent_for_customer(customer.id, limit=10)

    if not menus:
        await message.answer("📚 <b>Ваш архив пуст.</b>\n<i>Создайте первый сет командой /new</i>", parse_mode="HTML")
        return

    builder = InlineKeyboardBuilder()
    for m in menus:
        status_emoji = "🟢" if m.status == MenuStatus.COMPLETED else "🔴" if m.status == MenuStatus.FAILED else "🟡"
        btn_text = f"{status_emoji} Сет #{m.id} ({m.created_at:%d.%m})"
        builder.button(text=btn_text, callback_data=MenuAction(action="view", menu_id=m.id))

    builder.adjust(1)

    await message.answer(
        "📚 <b>Архив ваших гастрономических сетов:</b>\n<i>Выберите сет для просмотра или управления:</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )