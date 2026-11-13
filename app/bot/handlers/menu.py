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
    - Interactive gift delivery with spoilers and chef mode webapp integration
==========================================================
"""

from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.handlers.wallpaper import text_for
from app.bot.helpers import current_customer
from app.config import Settings
from app.database import async_session_maker
from app.database.models import Customer, ItemCategory, Menu, MenuStatus
from app.database.repositories import MenuRepository
from app.services.cuisine_catalog import CUISINES, cuisine_menu
from app.services.menu_delivery import MenuDeliveryUnavailable, paid_menu_documents
from app.services.menu_wizard import (
    DEFAULT_VISUAL_STYLE,
    MEAL_FULL_DAY,
    meal_label,
    meal_slot_label,
    parse_menu_plan,
)
from app.services.storage import InvalidImageError, PhotoTransferUnavailable, StorageService
from app.workers.menu_pipeline import MenuPipeline

logger = logging.getLogger(__name__)
router = Router(name="menu")


async def _photo_status_notice(message: Message, text: str) -> None:
    """An unreachable Telegram sendMessage must not abort photo persistence."""
    try:
        await asyncio.wait_for(message.answer(text), timeout=8)
    except (TelegramNetworkError, TimeoutError):
        logger.warning("Menu photo status notice timed out; continuing to save image")



class PremiumMenuStates(StatesGroup):
    waiting_for_dish_list = State()
    waiting_for_cover = State()
    waiting_for_spread = State()


async def begin_menu_entry(
        state: FSMContext,
        menu_id: int,
        category: ItemCategory = ItemCategory.MAIN,
) -> None:
    """Compatibility entry used by older integrations."""
    await state.set_state(PremiumMenuStates.waiting_for_dish_list)
    await state.update_data(menu_id=menu_id, category=category.value)


class MenuAction(CallbackData, prefix="menu"):
    action: str
    menu_id: int
    category: str | None = None


class LegacyMenuSetupAction(CallbackData, prefix="menu_setup"):
    """Decode buttons left in chats by the previous step-by-step wizard."""

    action: str
    value: str | None = None


async def begin_menu_setup(
        message: Message,
        state: FSMContext,
        customer: Customer,
        language: str = "ru",
) -> None:
    async with async_session_maker() as session:
        repo = MenuRepository(session)
        created = await repo.create(
            customer,
            meal_period=MEAL_FULL_DAY,
            visual_style=DEFAULT_VISUAL_STYLE,
        )
        menu = await repo.get(created.id, full=True)
    await state.set_state(None)
    await state.update_data(ui_lang=language, menu_id=menu.id)
    await message.answer(
        format_premium_dashboard(menu),
        reply_markup=build_dashboard_kb(menu),
        parse_mode="HTML",
    )


@router.callback_query(LegacyMenuSetupAction.filter(F.action.in_(["meal", "style"])))
async def upgrade_legacy_menu_setup(
        callback: CallbackQuery,
        state: FSMContext,
        session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Turn a click on an old wizard button into the new full-day draft."""
    async with session_factory() as session:
        customer = await current_customer(session, callback.from_user.id)
    if customer is None:
        await callback.answer("Сначала выполните /start", show_alert=True)
        return
    language = getattr(customer.language, "value", customer.language) or "ru"
    await begin_menu_setup(callback.message, state, customer, str(language))
    await callback.answer("Мастер обновлён: меню теперь вводится одним списком")


def format_premium_dashboard(menu: Menu) -> str:
    """Формирует премиальный текстовый интерфейс дашборда на основе реальных данных БД."""
    status_icon = "⚫️" if menu.status == MenuStatus.DRAFT else "⚜️️"
    status_text = "Формирование" if menu.status == MenuStatus.DRAFT else str(menu.status).capitalize()

    language = getattr(getattr(menu, "customer", None), "language", "ru")
    language = getattr(language, "value", language) or "ru"
    lines = [
        f"⚜️ <b>{meal_label(menu.meal_period, language)} · #{menu.id}</b>",
        f"Статус: {status_icon} <i>{status_text}</i>",
        ""
    ]

    lines.append(
        f"⚙️ Персон: {getattr(menu, 'servings', 2)} · "
        f"Настроение: {getattr(menu, 'menu_mood', 'romantic')} · "
        f"Тема: {getattr(menu, 'visual_style', 'premium_dark')}"
    )
    lines.append("")
    cover_status = "✅ Загружена" if menu.cover_photo_path else "❌ Отсутствует"
    spread_status = "✅ Загружен" if menu.spread_photo_path else "❌ Отсутствует"
    lines.append(f"🖼 Обложка: {cover_status}")
    lines.append(f"📔 Разворот: {spread_status}")
    lines.append("")

    grouped: dict[str, list[str]] = {}
    for item in menu.items:
        if item.title != "—":
            slot = item.meal_slot or "other"
            grouped.setdefault(slot, []).append(item.title)
    lines.append("<b>Состав меню:</b>")
    for slot in ("breakfast", "lunch", "dinner", "other"):
        titles = grouped.get(slot, [])
        if titles:
            lines.append(f"  • <b>{meal_slot_label(slot, language)}</b>: {len(titles)}")
            lines.extend(
                f"      {index}. {escape(title)}"
                for index, title in enumerate(titles, start=1)
            )

    lines.extend([
        "",
        "<i>Нейросеть автоматически подберет рецептуру, сформирует</i>",
        "<i>консолидированный лист закупок и стилизует иллюстрации.</i>"
    ])

    return "\n".join(lines)


def build_dashboard_kb(menu: Menu) -> InlineKeyboardMarkup:
    """Генерирует инлайн-клавиатуру для управления сетом."""
    builder = InlineKeyboardBuilder()

    # Основные действия меню. Каждая кнопка добавляется ровно один раз.
    builder.button(
        text="🍽 Выбрать категорию",
        callback_data=MenuAction(
            action="pick_category",
            menu_id=menu.id,
        ),
    )
    builder.button(
        text="✍️ Ввести блюда самостоятельно",
        callback_data=MenuAction(action="bulk_items", menu_id=menu.id),
    )
    builder.button(
        text="🌍 Выбрать кухню мира",
        callback_data=MenuAction(action="choose_cuisine", menu_id=menu.id),
    )
    builder.button(
        text="⚙️ Настроить вечер",
        callback_data=MenuAction(action="preferences", menu_id=menu.id),
    )
    builder.button(
        text="ℹ️ Требования к генерации",
        callback_data=MenuAction(
            action="requirements",
            menu_id=menu.id,
        ),
    )

    builder.button(
        text=("✅ Фото обложки" if menu.cover_photo_path else "🖼 Загрузить фото обложки"),
        callback_data=MenuAction(action="req_cover", menu_id=menu.id)
    )
    builder.button(
        text=("✅ Фото разворота" if menu.spread_photo_path else "📔 Загрузить фото разворота"),
        callback_data=MenuAction(action="req_spread", menu_id=menu.id)
    )

    item_count = sum(item.title != "—" for item in menu.items)
    builder.button(
        text=f"{'✅' if item_count else '📝'} Ввести меню · {item_count} блюд",
        callback_data=MenuAction(action="edit_plan", menu_id=menu.id),
    )

    can_generate = bool(menu.items and menu.cover_photo_path and menu.spread_photo_path)

    if menu.status in (MenuStatus.DRAFT, MenuStatus.FAILED, MenuStatus.QUEUED):
        if can_generate:
            builder.button(
                text="✨ Сформировать",
                callback_data=MenuAction(action="generate", menu_id=menu.id)
            )
        else:
            # Кнопка открывает понятную подсказку; не используем устаревший
            # Старый callback без идентификатора меню больше не используется.
            builder.button(
                text="⚠️ Добавьте блюда и два фото",
                callback_data=MenuAction(
                    action="requirements",
                    menu_id=menu.id,
                ),
            )

    if getattr(menu, "is_paid", False) and menu.status in (
        MenuStatus.PAID,
        MenuStatus.PARTIAL_SUCCESS,
        MenuStatus.COMPLETED,
        MenuStatus.FAILED,
    ):
        builder.button(
            text="📩 Получить готовые файлы повторно",
            callback_data=MenuAction(action="resend", menu_id=menu.id),
        )

    builder.button(text="⬅️ Назад", callback_data="prod_food_porn")
    builder.button(text="🏠 В начало", callback_data="back_to_products")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(MenuAction.filter(F.action == "resend"))
async def resend_paid_menu(
    callback: CallbackQuery,
    callback_data: MenuAction,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Resend saved PDFs; never re-enter the AI pipeline or payment flow."""
    async with session_factory() as session:
        menu = await MenuRepository(session).get(callback_data.menu_id, full=True)

    if not _owned_by(menu, callback.from_user.id):
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    try:
        booklet, recipes = paid_menu_documents(menu)
    except MenuDeliveryUnavailable:
        await callback.answer(
            "Готовые файлы недоступны. Обратитесь в поддержку; повторно оплачивать не нужно.",
            show_alert=True,
        )
        return

    await callback.answer("Отправляем сохранённые файлы.")
    try:
        await callback.bot.send_document(
            chat_id=callback.from_user.id,
            document=FSInputFile(str(booklet)),
            request_timeout=180,
        )
        await callback.bot.send_document(
            chat_id=callback.from_user.id,
            document=FSInputFile(str(recipes)),
            request_timeout=180,
        )
    except Exception:
        logger.exception("Paid menu resend failed for order %s", menu.id)
        await callback.message.answer(
            "Не удалось доставить файлы. Заказ и оплата сохранены; попробуйте позже."
        )
        return

    async with session_factory() as session:
        await MenuRepository(session).set_status(menu.id, MenuStatus.COMPLETED)
    await callback.message.answer("Оба документа повторно отправлены. 💛")


@router.callback_query(MenuAction.filter(F.action == "requirements"))
async def show_generation_requirements(
    callback: CallbackQuery,
    callback_data: MenuAction,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Показывает, какие данные ещё нужны для запуска генерации."""
    async with session_factory() as session:
        menu = await MenuRepository(session).get(callback_data.menu_id, full=True)

    if not _owned_by(menu, callback.from_user.id):
        await callback.answer("Сет не найден.", show_alert=True)
        return

    missing = []
    if not any(item.title != "—" for item in menu.items):
        missing.append("добавьте хотя бы одно блюдо")
    if not menu.cover_photo_path:
        missing.append("загрузите фото обложки")
    if not menu.spread_photo_path:
        missing.append("загрузите фото разворота")

    if missing:
        message = "Чтобы запустить генерацию, " + ", ".join(missing) + "."
    else:
        message = "Всё готово. Можно запускать генерацию."

    await callback.answer(message, show_alert=True)


async def explain_legacy_generation_requirements(callback: CallbackQuery) -> None:
    """Совместимость со старой кнопкой: точный текст для устаревшего сценария."""
    await callback.answer(
        "Добавьте хотя бы одно блюдо и загрузите фото обложки и разворота.",
        show_alert=True,
    )


# Оставляем прежнее имя для интеграций, которые могли импортировать функцию напрямую.
explain_generation_requirements = explain_legacy_generation_requirements


# --- НОВЫЕ ИНТЕРАКТИВНЫЕ ФУНКЦИИ (на уровне модуля) ---

def format_gift_delivery_text(menu: Menu) -> str:
    """Формирует текст подарка для супруга с сокрытием блюд под спойлерами."""
    lines = [
        "⚜️ <b>Ваш персональний Гастрономічний Сет</b> ⚜️",
        "<i>Кохана людина підготувала для вас тиждень вишуканої смакової турботи.</i>\n",
        "<b>Меню страв на цей тиждень:</b>"
    ]

    for idx, item in enumerate(menu.items, start=1):
        lines.append(f"<b>Вечеря {idx}:</b> <tg-spoiler>{item.title}</tg-spoiler>")
        if item.romantic_price:
            lines.append(f"💌 <i>Ціна задоволення: {item.romantic_price}</i>\n")

    lines.append("Натисніть кнопку нижче, коли розпочнете готування, або сповістіть партнера про готовність.")
    return "\n".join(lines)


def get_cooking_webapp_keyboard(menu_id: int, miniapp_url: str) -> InlineKeyboardMarkup:
    """Клавиатура для открытия Mini App (режим Шеф-повара) и отчета о готовности."""
    url = f"{miniapp_url.rstrip('/')}/cook/{menu_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🍳 Відкрити режим Шеф-кухаря", web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton(text="✅ Блюдо подано (Повідомити)", callback_data=f"dish_ready_{menu_id}")]
    ])


@router.callback_query(F.data.startswith("dish_ready_"))
async def notify_partner_about_meal(callback: CallbackQuery) -> None:
    """Хендер уведомления дарящего о том, что ужин готов."""
    menu_id = int(callback.data.removeprefix("dish_ready_"))

    async with async_session_maker() as session:
        menu = await session.get(Menu, menu_id)
        if not menu:
            await callback.answer("Меню не знайдено.", show_alert=True)
            return

        customer = await session.get(Customer, menu.customer_id)
        if not customer:
            await callback.answer("Дані про замовника відсутні.", show_alert=True)
            return

        giver_telegram_id = customer.telegram_user_id

    try:
        await callback.bot.send_message(
            chat_id=giver_telegram_id,
            text=(
                "🥂 <b>Ваш шеф-повар повідомляє, що вечеря готова!</b>\n\n"
                "Саме час сідати за стіл і насолоджуватися моментом. "
                "Не забудьте сплатити романтичну «вартість» цього шедевра! 💛"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    await callback.answer("🎉 Повідомлення успішно надіслано вашому партнеру!", show_alert=True)


# --- ПОШАГОВЫЙ МАСТЕР МЕНЮ ---


def _owned_by(menu: Menu | None, telegram_user_id: int) -> bool:
    return bool(
        menu
        and getattr(menu, "customer", None)
        and menu.customer.telegram_user_id == telegram_user_id
    )


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

    if not _owned_by(menu, callback.from_user.id):
        await callback.answer("Сет не найден.", show_alert=True)
        return

    await callback.message.edit_text(
        format_premium_dashboard(menu),
        reply_markup=build_dashboard_kb(menu),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(MenuAction.filter(F.action == "choose_cuisine"))
async def choose_cuisine(
    callback: CallbackQuery,
    callback_data: MenuAction,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        menu = await MenuRepository(session).get(callback_data.menu_id, full=True)
    if not _owned_by(menu, callback.from_user.id):
        await callback.answer("Сет не найден.", show_alert=True)
        return
    if menu.status not in (MenuStatus.DRAFT, MenuStatus.FAILED):
        await callback.answer("Готовый заказ нельзя изменять.", show_alert=True)
        return
    language = getattr(menu.customer.language, "value", menu.customer.language) or "ru"
    builder = InlineKeyboardBuilder()
    for cuisine in CUISINES:
        builder.button(
            text=cuisine.label(str(language)),
            callback_data=MenuAction(
                action="cuisine", menu_id=menu.id, category=cuisine.code,
            ),
        )
    builder.button(text="⬅️ Назад", callback_data=MenuAction(action="view", menu_id=menu.id))
    builder.adjust(2, 2, 2, 2, 1)
    await callback.message.edit_text(
        text_for(
            str(language),
            "🌍 <b>Оберіть кухню світу</b>\\n"
            "Я запропоную цілісне меню із закускою, основною стравою, "
            "напоєм і десертом. Список можна змінити перед генерацією.",
            "🌍 <b>Выберите кухню мира</b>\\n"
            "Я предложу цельный набор с закуской, основным блюдом, "
            "напитком и десертом. Список можно изменить до генерации.",
            "🌍 <b>Choose a cuisine</b>\\n"
            "I'll suggest a cohesive menu with starter, main course, "
            "drink and dessert. You can edit it before generation.",
        ),
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(MenuAction.filter(F.action == "cuisine"))
async def apply_cuisine(
    callback: CallbackQuery,
    callback_data: MenuAction,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        repo = MenuRepository(session)
        menu = await repo.get(callback_data.menu_id, full=True)
        if not _owned_by(menu, callback.from_user.id):
            await callback.answer("Сет не найден.", show_alert=True)
            return
        if menu.status not in (MenuStatus.DRAFT, MenuStatus.FAILED):
            await callback.answer("Готовый заказ нельзя изменять.", show_alert=True)
            return
        language = getattr(menu.customer.language, "value", menu.customer.language) or "ru"
        try:
            entries = cuisine_menu(
                callback_data.category or "", str(language),
                drinks=menu.include_drinks, dessert=menu.include_dessert,
            )
        except ValueError:
            await callback.answer("Кухня не найдена.", show_alert=True)
            return
        await repo.set_premium_preferences(
            menu.id,
            selection_mode="cuisine",
            selected_cuisine=callback_data.category,
        )
        await repo.replace_menu_plan(
            menu_id=menu.id,
            entries=[(entry.meal_slot, entry.title, entry.category) for entry in entries],
        )
        menu = await repo.get(menu.id, full=True)
    await callback.message.edit_text(
        "✅ " + format_premium_dashboard(menu)
        + "\\n\\n<i>Состав предложен автоматически. "
        "При необходимости измените блюда вручную до генерации.</i>",
        reply_markup=build_dashboard_kb(menu), parse_mode="HTML",
    )
    await callback.answer("Подборка добавлена. Можно редактировать.")


def _premium_preferences_keyboard(menu: Menu) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for number in (1, 2, 4, 6):
        builder.button(
            text=("✅ " if menu.servings == number else "") + f"{number} персон",
            callback_data=MenuAction(
                action="pref", menu_id=menu.id, category=f"servings:{number}",
            ),
        )
    for mood, label in (
        ("romantic", "💌 Романтический"), ("cozy", "🏡 Уютный"),
        ("festive", "🎉 Праздничный"), ("light", "🌿 Лёгкий"),
        ("refined", "✨ Изысканный"),
    ):
        builder.button(
            text=("✅ " if menu.menu_mood == mood else "") + label,
            callback_data=MenuAction(
                action="pref", menu_id=menu.id, category=f"mood:{mood}",
            ),
        )
    for theme, label in (
        ("premium_dark", "🌙 Тёмный"),
        ("premium_light", "☀️ Светлый"),
        ("premium_colorful", "🎨 Цветной"),
    ):
        builder.button(
            text=("✅ " if menu.visual_style == theme else "") + label,
            callback_data=MenuAction(
                action="pref", menu_id=menu.id, category=f"style:{theme}",
            ),
        )
    if menu.selection_mode == "cuisine" and menu.selected_cuisine:
        for key, label, enabled in (
            ("drinks", "🥂 Напитки", menu.include_drinks),
            ("dessert", "🍰 Десерт", menu.include_dessert),
        ):
            builder.button(
                text=("✅ " if enabled else "⬜ ") + label,
                callback_data=MenuAction(
                    action="pref", menu_id=menu.id, category=f"{key}:toggle",
                ),
            )
    builder.button(
        text="⬅️ Вернуться к меню",
        callback_data=MenuAction(action="view", menu_id=menu.id),
    )
    builder.adjust(2)
    return builder.as_markup()


@router.callback_query(MenuAction.filter(F.action == "preferences"))
async def show_premium_preferences(
    callback: CallbackQuery,
    callback_data: MenuAction,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        menu = await MenuRepository(session).get(callback_data.menu_id, full=True)
    if not _owned_by(menu, callback.from_user.id):
        await callback.answer("Сет не найден.", show_alert=True)
        return
    if menu.status not in (MenuStatus.DRAFT, MenuStatus.FAILED) or menu.is_paid:
        await callback.answer("Оплаченный или выполняемый заказ нельзя изменить.", show_alert=True)
        return
    await callback.message.edit_text(
        "<b>⚙️ Настройте ваш вечер</b>\\n"
        "Выберите количество гостей, настроение и оформление.\\n"
        "<i>В подборке кухни мира можно включить или отключить напитки и десерт.</i>",
        parse_mode="HTML",
        reply_markup=_premium_preferences_keyboard(menu),
    )
    await callback.answer()


@router.callback_query(MenuAction.filter(F.action == "pref"))
async def change_premium_preference(
    callback: CallbackQuery,
    callback_data: MenuAction,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    value = callback_data.category or ""
    predefined = {
        **{f"servings:{n}": {"servings": n} for n in (1, 2, 4, 6)},
        **{f"mood:{m}": {"menu_mood": m} for m in (
            "romantic", "cozy", "festive", "light", "refined",
        )},
        **{f"style:{theme}": {"visual_style": theme} for theme in (
            "premium_dark", "premium_light", "premium_colorful",
        )},
    }
    async with session_factory() as session:
        repo = MenuRepository(session)
        menu = await repo.get(callback_data.menu_id, full=True)
        if not _owned_by(menu, callback.from_user.id):
            await callback.answer("Сет не найден.", show_alert=True)
            return
        if menu.status not in (MenuStatus.DRAFT, MenuStatus.FAILED) or menu.is_paid:
            await callback.answer("Заказ нельзя изменить.", show_alert=True)
            return
        if value == "drinks:toggle" and menu.selection_mode == "cuisine":
            changes = {"include_drinks": not menu.include_drinks}
        elif value == "dessert:toggle" and menu.selection_mode == "cuisine":
            changes = {"include_dessert": not menu.include_dessert}
        else:
            changes = predefined.get(value)
        if not changes:
            await callback.answer("Неизвестная настройка.", show_alert=True)
            return
        await repo.set_premium_preferences(menu.id, **changes)
        # Toggling optional courses updates the proposed cuisine menu;
        # do not modify custom, manually entered dishes.
        if (
            menu.selection_mode == "cuisine"
            and menu.selected_cuisine
            and ("include_drinks" in changes or "include_dessert" in changes)
        ):
            entries = cuisine_menu(
                menu.selected_cuisine,
                str(getattr(menu.customer.language, "value", menu.customer.language)),
                drinks=menu.include_drinks, dessert=menu.include_dessert,
            )
            await repo.replace_menu_plan(
                menu_id=menu.id,
                entries=[(e.meal_slot, e.title, e.category) for e in entries],
            )
        menu = await repo.get(menu.id, full=True)
    await callback.message.edit_text(
        "<b>⚙️ Настройте ваш вечер</b>\\n"
        "Выберите количество гостей, настроение и оформление.",
        parse_mode="HTML", reply_markup=_premium_preferences_keyboard(menu),
    )
    await callback.answer("Сохранено")


@router.callback_query(MenuAction.filter(F.action.in_(["edit_plan", "edit_category", "bulk_items"])))
async def prompt_menu_plan(
        callback: CallbackQuery,
        callback_data: MenuAction,
        state: FSMContext,
        session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        menu = await MenuRepository(session).get(callback_data.menu_id, full=True)
    if not _owned_by(menu, callback.from_user.id):
        await callback.answer("Сет не найден.", show_alert=True)
        return
    language = getattr(menu.customer.language, "value", menu.customer.language)
    await state.set_state(PremiumMenuStates.waiting_for_dish_list)
    await state.update_data(
        menu_id=callback_data.menu_id,
        ui_lang=language,
    )
    await callback.message.edit_text(
        text_for(
            language,
            "🖋 <b>Введіть усе меню одним повідомленням</b>\n\n"
            "Заголовки <b>Сніданок, Обід, Вечеря</b> не вважаються стравами. "
            "Кожен інший рядок — окрема страва. Маркери, тире та нумерація дозволені.\n\n"
            "Можна змішувати мови, використовувати трансліт і допускати невеликі помилки.\n\n"
            "<pre>Сніданок\n- Омлет\nКава\n\nОбід:\n1. Борщ\nСалат Цезар\n\nВечеря\nСтейк\nЧервоне вино</pre>",
            "🖋 <b>Введите всё меню одним сообщением</b>\n\n"
            "Заголовки <b>Завтрак, Обед, Ужин</b> не считаются блюдами. "
            "Каждая другая строка — отдельное блюдо. Маркеры, тире и нумерация допустимы.\n\n"
            "Можно смешивать языки, использовать транслит и допускать небольшие опечатки.\n\n"
            "<pre>Завтрак\n- Омлет\nКофе\n\nОбед:\n1. Борщ\nСалат Цезарь\n\nУжин\nСтейк\nКрасное вино</pre>",
            "🖋 <b>Send the entire menu in one message</b>\n\n"
            "The headings <b>Breakfast, Lunch, Dinner</b> are separators, not dishes. "
            "Every other line is one dish. Bullets, dashes, and numbering are allowed.\n\n"
            "Languages may be mixed; transliteration and minor typos are accepted.\n\n"
            "<pre>Breakfast\n- Omelet\nCoffee\n\nLunch:\n1. Soup\nCaesar salad\n\nDinner\nSteak\nRed wine</pre>",
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=MenuAction(action="view", menu_id=menu.id).pack())],
            [InlineKeyboardButton(text="🏠 В начало", callback_data="back_to_products")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(PremiumMenuStates.waiting_for_dish_list, F.text)
async def receive_dish_list(
        message: Message,
        state: FSMContext,
        session_factory: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    menu_id = data.get("menu_id")
    language = data.get("ui_lang", "ru")
    try:
        entries = parse_menu_plan(message.text, language=language)
    except (ValueError, TypeError) as exc:
        await message.answer(
            text_for(
                language,
                f"⚠️ Не вдалося розпізнати меню: {exc}.\nДодайте від 1 до 18 страв — кожну з нового рядка.",
                f"⚠️ Не удалось распознать меню: {exc}.\nДобавьте от 1 до 18 блюд — каждое с новой строки.",
                f"⚠️ Could not parse the menu: {exc}.\nAdd 1 to 18 dishes, one per line.",
            )
        )
        return
    async with session_factory() as session:
        repo = MenuRepository(session)
        menu = await repo.get(menu_id, full=True)
        if not _owned_by(menu, message.from_user.id):
            await state.clear()
            await message.answer("Сет не найден. Вернитесь в /start.")
            return
        await repo.set_premium_preferences(
            menu_id, selection_mode="manual", selected_cuisine=None,
        )
        await repo.replace_menu_plan(
            menu_id=menu_id,
            entries=[(entry.meal_slot, entry.title, entry.category) for entry in entries],
        )
        menu = await repo.get(menu_id, full=True)
    await state.set_state(None)
    await message.answer(
        format_premium_dashboard(menu),
        reply_markup=build_dashboard_kb(menu),
        parse_mode="HTML",
    )


@router.callback_query(MenuAction.filter(F.action.in_(["req_cover", "req_spread"])))
async def prompt_photo(
        callback: CallbackQuery,
        callback_data: MenuAction,
        state: FSMContext,
        session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        menu = await MenuRepository(session).get(callback_data.menu_id, full=True)
    if not _owned_by(menu, callback.from_user.id):
        await callback.answer("Сет не найден.", show_alert=True)
        return
    is_cover = callback_data.action == "req_cover"
    target_state = PremiumMenuStates.waiting_for_cover if is_cover else PremiumMenuStates.waiting_for_spread
    role_name = "обложки" if is_cover else "разворота"

    await state.set_state(target_state)
    await state.update_data(menu_id=callback_data.menu_id)

    await callback.message.edit_text(
        f"🖼 <b>Отправьте фотографию для {role_name}</b>\n\n"
        "Лицо должно быть хорошо видно, без сильных фильтров. "
        "Лучше использовать вертикальный кадр, снятый не сверху.\n\n"
        "<i>Отправьте именно фото, а не документ.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=MenuAction(action="view", menu_id=menu.id).pack())],
            [InlineKeyboardButton(text="🏠 В начало", callback_data="back_to_products")],
        ]),
        parse_mode="HTML",
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

    role_label = "обложки" if role == "cover" else "разворота"
    # Send feedback before either the Neon query or Telegram download.
    await _photo_status_notice(
        message,
        f"📥 Фото для {role_label} получено. "
        "Проверяю заказ и загружаю файл…",
    )
    try:
        async with session_factory() as session:
            existing = await MenuRepository(session).get(menu_id, full=True)
    except SQLAlchemyError:
        logger.exception("Menu photo ownership lookup failed for menu %s", menu_id)
        await _photo_status_notice(
            message, "⚠️ База данных временно недоступна. "
            "Фото ещё не сохранено, повторите отправку позже.",
        )
        return
    if not _owned_by(existing, message.from_user.id):
        await state.clear()
        await message.answer("Сет не найден. Вернитесь в /start.")
        return

    try:
        path = await StorageService(settings).save_telegram_photo(
            bot, message.photo[-1].file_id, menu_id=menu_id, role=role
        )
    except InvalidImageError:
        await message.answer(
            f"⚠️ Ошибка формата. Загрузите корректное фото (до {settings.max_upload_mb} MB)."
        )
        return
    except PhotoTransferUnavailable:
        logger.warning(
            "Menu photo cannot be downloaded from Telegram: menu=%s role=%s",
            menu_id, role,
        )
        await message.answer(
            f"⚠️ Telegram не передал фото для {role_label}. "
            "Сет сохранён, повторите отправку этого фото. "
            "Повторно создавать заказ не нужно."
        )
        return

    try:
        async with session_factory() as session:
            repo = MenuRepository(session)
            kwargs = (
                {"cover": str(path), "cover_file_id": message.photo[-1].file_id}
                if role == "cover"
                else {"spread": str(path), "spread_file_id": message.photo[-1].file_id}
            )
            await repo.set_photos(menu_id, **kwargs)
            menu = await repo.get(menu_id, full=True)
    except SQLAlchemyError:
        logger.exception("Menu photo DB persistence failed for menu %s", menu_id)
        await _photo_status_notice(
            message, "⚠️ Фото получено, но база данных сейчас недоступна. "
            "Попробуйте повторить отправку позже; новый заказ не нужен.",
        )
        return

    await state.set_state(None)
    await _photo_status_notice(
        message, f"✅ Фото для {role_label} сохранено. Обновляю карточку сета."
    )
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

        if not _owned_by(menu, callback.from_user.id):
            await callback.answer("Сет не найден.", show_alert=True)
            return
        if menu.status == MenuStatus.COMPLETED:
            await callback.answer("Сет уже успешно завершен.", show_alert=True)
            return
        if menu.status == MenuStatus.QUEUED:
            # A crashed worker can leave QUEUED forever. Lease state, not
            # QUEUED alone, determines whether another worker is active.
            active = await session.scalar(
                select(Menu.id).where(
                    Menu.id == menu.id,
                    Menu.processing_token.is_not(None),
                    Menu.processing_lease_until > func.now(),
                )
            )
            if active is not None:
                await callback.answer("Сет уже формируется.", show_alert=True)
                return
            await pipeline.submit(menu.id, callback.from_user.id)
            await callback.answer("Повторно запускаю обработку этого же сета.")
            return
        if not menu.items or not menu.cover_photo_path or not menu.spread_photo_path:
            await callback.answer("Добавьте блюда и загрузите два фото.", show_alert=True)
            return

        await repo.set_status(menu.id, MenuStatus.QUEUED)

    await callback.message.edit_text(
        f"⚜️️ <b>Гастрономический сет #{menu.id}</b>\n"
        f"Статус: 🟡 <i>Утвержден, отправлен в нейросети</i>\n\n"
        f"<i>Алгоритмы генерируют рецепты и консолидируют лист закупок.\nОжидайте готовый PDF-документ.</i>",
        parse_mode="HTML"
    )

    await pipeline.submit(menu.id, callback.from_user.id)
    await state.clear()
    await callback.answer("Отправлено в обработку")


async def send_history(
        message: Message,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        telegram_user_id: int | None = None,
) -> None:
    telegram_user_id = telegram_user_id or message.from_user.id
    async with session_factory() as session:
        customer = await current_customer(session, telegram_user_id)
        if not customer:
            return

        menus = await MenuRepository(session).recent_for_customer(customer.id, limit=10)

    if not menus:
        await message.answer(
            "📚 <b>Ваш архив пуст.</b>\n<i>Создайте первый сет через главное меню.</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🍽 Создать меню", callback_data="prod_food_porn")],
                [InlineKeyboardButton(text="🏠 В начало", callback_data="back_to_products")],
            ]),
            parse_mode="HTML",
        )
        return

    builder = InlineKeyboardBuilder()
    for m in menus:
        status_emoji = "🟢" if m.status == MenuStatus.COMPLETED else "🔴" if m.status == MenuStatus.FAILED else "🟡"
        btn_text = f"{status_emoji} Сет #{m.id} ({m.created_at:%d.%m})"
        builder.button(text=btn_text, callback_data=MenuAction(action="view", menu_id=m.id))

    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🏠 В начало", callback_data="back_to_products"))

    await message.answer(
        "📚 <b>Архив ваших гастрономических сетов:</b>\n<i>Выберите сет для просмотра или управления:</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(Command("history"))
async def history_command(
        message: Message,
        session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await send_history(message, session_factory)


@router.callback_query(F.data == "home_orders")
async def history_callback(
        callback: CallbackQuery,
        session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await send_history(
        callback.message,
        session_factory,
        telegram_user_id=callback.from_user.id,
    )
    await callback.answer()
