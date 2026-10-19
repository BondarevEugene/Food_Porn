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

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.handlers.wallpaper import text_for
from app.bot.helpers import current_customer
from app.config import Settings
from app.database import async_session_maker
from app.database.models import Customer, ItemCategory, Menu, MenuStatus
from app.database.repositories import MenuRepository
from app.services.menu_wizard import (
    MEAL_BREAKFAST,
    MEAL_DINNER,
    STYLE_LABELS,
    category_rule,
    meal_label,
    meal_rules,
    normalize_dish_lines,
    style_label,
)
from app.services.storage import InvalidImageError, StorageService
from app.workers.menu_pipeline import MenuPipeline

logger = logging.getLogger(__name__)
router = Router(name="menu")


class PremiumMenuStates(StatesGroup):
    choosing_meal = State()
    choosing_style = State()
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


class MenuSetupAction(CallbackData, prefix="menu_setup"):
    action: str
    value: str | None = None


class MenuAction(CallbackData, prefix="menu"):
    action: str
    menu_id: int
    category: str | None = None


def build_meal_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text_for(language, "☀️ Сніданок", "☀️ Завтрак", "☀️ Breakfast"), callback_data=MenuSetupAction(action="meal", value=MEAL_BREAKFAST).pack())],
        [InlineKeyboardButton(text=text_for(language, "🌙 Вечеря", "🌙 Ужин", "🌙 Dinner"), callback_data=MenuSetupAction(action="meal", value=MEAL_DINNER).pack())],
        [InlineKeyboardButton(text=text_for(language, "⬅️ Назад", "⬅️ Назад", "⬅️ Back"), callback_data="back_to_products")],
    ])


def build_style_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"{index}. {labels.get(language, labels['ru'])}",
        callback_data=MenuSetupAction(action="style", value=style).pack(),
    )] for index, (style, labels) in enumerate(STYLE_LABELS.items(), start=1)]
    rows.append([InlineKeyboardButton(text=text_for(language, "⬅️ Назад", "⬅️ Назад", "⬅️ Back"), callback_data=MenuSetupAction(action="back_meal").pack())])
    rows.append([InlineKeyboardButton(text=text_for(language, "🏠 На головну", "🏠 В начало", "🏠 Home"), callback_data="back_to_products")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def begin_menu_setup(message: Message, state: FSMContext, language: str = "ru") -> None:
    await state.set_state(PremiumMenuStates.choosing_meal)
    await state.update_data(ui_lang=language)
    await message.answer(
        text_for(language, "🍽 <b>Створення меню</b>\n\nОберіть, яке меню створюємо:", "🍽 <b>Создание меню</b>\n\nВыберите, какое меню создаём:", "🍽 <b>Create a menu</b>\n\nChoose the menu type:"),
        reply_markup=build_meal_keyboard(language), parse_mode="HTML",
    )


def format_premium_dashboard(menu: Menu) -> str:
    """Формирует премиальный текстовый интерфейс дашборда на основе реальных данных БД."""
    status_icon = "⚫️" if menu.status == MenuStatus.DRAFT else "⚜️️"
    status_text = "Формирование" if menu.status == MenuStatus.DRAFT else str(menu.status).capitalize()

    language = getattr(getattr(menu, "customer", None), "language", "ru")
    language = getattr(language, "value", language) or "ru"
    lines = [
        f"⚜️ <b>{meal_label(menu.meal_period, language)} · #{menu.id}</b>",
        f"Статус: {status_icon} <i>{status_text}</i>",
        f"Образ: <i>{style_label(menu.visual_style, language)}</i>",
        ""
    ]

    cover_status = "✅ Загружена" if menu.cover_photo_path else "❌ Отсутствует"
    spread_status = "✅ Загружен" if menu.spread_photo_path else "❌ Отсутствует"
    lines.append(f"🖼 Обложка: {cover_status}")
    lines.append(f"📔 Разворот: {spread_status}")
    lines.append("")

    counts = {rule.category: 0 for rule in meal_rules(menu.meal_period)}
    for item in menu.items:
        if item.title != "—" and item.category in counts:
            counts[item.category] += 1
    lines.append("<b>Состав:</b>")
    for rule in meal_rules(menu.meal_period):
        lines.append(f"  • {rule.label(language)}: {counts[rule.category]} / {rule.limit}")

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
        text=("✅ Фото обложки" if menu.cover_photo_path else "🖼 Загрузить фото обложки"),
        callback_data=MenuAction(action="req_cover", menu_id=menu.id)
    )
    builder.button(
        text=("✅ Фото разворота" if menu.spread_photo_path else "📔 Загрузить фото разворота"),
        callback_data=MenuAction(action="req_spread", menu_id=menu.id)
    )

    counts = {rule.category: 0 for rule in meal_rules(menu.meal_period)}
    for item in menu.items:
        if item.title != "—" and item.category in counts:
            counts[item.category] += 1
    language = getattr(getattr(menu, "customer", None), "language", "ru")
    language = getattr(language, "value", language) or "ru"
    for rule in meal_rules(menu.meal_period):
        count = counts[rule.category]
        builder.button(
            text=f"{'✅' if count else '▫️'} {rule.label(language)} · {count} / {rule.limit}",
            callback_data=MenuAction(action="edit_category", menu_id=menu.id, category=rule.category.value),
        )

    can_generate = bool(menu.items and menu.cover_photo_path and menu.spread_photo_path)

    if menu.status in (MenuStatus.DRAFT, MenuStatus.FAILED, MenuStatus.QUEUED):
        if can_generate:
            builder.button(
                text="✨ Сформировать",
                callback_data=MenuAction(action="generate", menu_id=menu.id)
            )
        else:
            builder.button(
                text="⚠️ Добавьте блюда и два фото",
                callback_data="ignore"
            )

    builder.button(text="⬅️ Назад", callback_data="prod_food_porn")
    builder.button(text="🏠 В начало", callback_data="back_to_products")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "ignore")
async def explain_generation_requirements(callback: CallbackQuery) -> None:
    """Объясняет, какие данные ещё нужны для запуска генерации."""
    await callback.answer(
        "Добавьте хотя бы одно блюдо и загрузите фото обложки и разворота.",
        show_alert=True,
    )


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


@router.callback_query(MenuSetupAction.filter(F.action == "meal"))
async def choose_meal_period(
    callback: CallbackQuery,
    callback_data: MenuSetupAction,
    state: FSMContext,
) -> None:
    if callback_data.value not in {MEAL_BREAKFAST, MEAL_DINNER}:
        await callback.answer("Неверный вариант", show_alert=True)
        return
    data = await state.get_data()
    language = data.get("ui_lang", "ru")
    await state.set_state(PremiumMenuStates.choosing_style)
    await state.update_data(meal_period=callback_data.value)
    await callback.message.edit_text(
        text_for(
            language,
            f"{meal_label(callback_data.value, language)}\n\nОберіть образ для оформлення:",
            f"{meal_label(callback_data.value, language)}\n\nВыберите образ для оформления:",
            f"{meal_label(callback_data.value, language)}\n\nChoose the visual style:",
        ),
        reply_markup=build_style_keyboard(language),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(MenuSetupAction.filter(F.action == "back_meal"))
async def back_to_meal_choice(callback: CallbackQuery, state: FSMContext) -> None:
    language = (await state.get_data()).get("ui_lang", "ru")
    await state.set_state(PremiumMenuStates.choosing_meal)
    await callback.message.edit_text(
        text_for(
            language,
            "🍽 <b>Створення меню</b>\n\nОберіть, яке меню створюємо:",
            "🍽 <b>Создание меню</b>\n\nВыберите, какое меню создаём:",
            "🍽 <b>Create a menu</b>\n\nChoose the menu type:",
        ),
        reply_markup=build_meal_keyboard(language),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(MenuSetupAction.filter(F.action == "style"))
async def choose_visual_style(
    callback: CallbackQuery,
    callback_data: MenuSetupAction,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if callback_data.value not in STYLE_LABELS:
        await callback.answer("Неверный образ", show_alert=True)
        return
    data = await state.get_data()
    language = data.get("ui_lang", "ru")
    meal_period = data.get("meal_period")
    if meal_period not in {MEAL_BREAKFAST, MEAL_DINNER}:
        await begin_menu_setup(callback.message, state, language)
        await callback.answer()
        return
    async with session_factory() as session:
        customer = await current_customer(session, callback.from_user.id)
        if customer is None:
            await callback.answer("Сначала выполните /start", show_alert=True)
            return
        repo = MenuRepository(session)
        created = await repo.create(
            customer,
            meal_period=meal_period,
            visual_style=callback_data.value,
        )
        menu = await repo.get(created.id, full=True)
    await state.set_state(None)
    await state.update_data(menu_id=menu.id, ui_lang=language)
    await callback.message.edit_text(
        format_premium_dashboard(menu),
        reply_markup=build_dashboard_kb(menu),
        parse_mode="HTML",
    )
    await callback.answer("Черновик создан")


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


@router.callback_query(MenuAction.filter(F.action == "edit_category"))
async def prompt_category_list(
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
    try:
        rule = category_rule(menu.meal_period, ItemCategory(callback_data.category))
    except (ValueError, LookupError):
        await callback.answer("Категория не найдена", show_alert=True)
        return
    language = getattr(menu.customer.language, "value", menu.customer.language)
    await state.set_state(PremiumMenuStates.waiting_for_dish_list)
    await state.update_data(
        menu_id=callback_data.menu_id,
        category=callback_data.category,
        category_limit=rule.limit,
        ui_lang=language,
    )
    await callback.message.edit_text(
        text_for(
            language,
            f"🖋 <b>{rule.label(language)}</b>\n\nНапишіть до {rule.limit} позицій — кожну з нового рядка.\nЯкщо категорія не потрібна, напишіть <code>пас</code>.",
            f"🖋 <b>{rule.label(language)}</b>\n\nНапишите до {rule.limit} позиций — каждую с новой строки.\nЕсли категория не нужна, напишите <code>пас</code>.",
            f"🖋 <b>{rule.label(language)}</b>\n\nSend up to {rule.limit} items, one per line.\nSend <code>pass</code> to clear this category.",
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
    category_val = data.get("category")
    language = data.get("ui_lang", "ru")
    try:
        category = ItemCategory(category_val)
        titles = normalize_dish_lines(
            message.text,
            limit=int(data.get("category_limit", 1)),
            language=language,
        )
    except (ValueError, TypeError):
        await message.answer("⚠️ Не удалось распознать список. Попробуйте ещё раз.")
        return
    async with session_factory() as session:
        repo = MenuRepository(session)
        menu = await repo.get(menu_id, full=True)
        if not _owned_by(menu, message.from_user.id):
            await state.clear()
            await message.answer("Сет не найден. Вернитесь в /start.")
            return
        await repo.replace_category_items(
            menu_id=menu_id,
            category=category,
            titles=titles,
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

    async with session_factory() as session:
        existing = await MenuRepository(session).get(menu_id, full=True)
    if not _owned_by(existing, message.from_user.id):
        await state.clear()
        await message.answer("Сет не найден. Вернитесь в /start.")
        return

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

        if not _owned_by(menu, callback.from_user.id):
            await callback.answer("Сет не найден.", show_alert=True)
            return
        if menu.status == MenuStatus.COMPLETED:
            await callback.answer("Сет уже успешно завершен.", show_alert=True)
            return
        if menu.status == MenuStatus.QUEUED:
            await callback.answer("Сет уже формируется.", show_alert=True)
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
