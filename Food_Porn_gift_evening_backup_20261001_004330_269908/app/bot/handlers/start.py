"""
==========================================================
FOOD_PORN & OLD MONEY MANIFESTATIONS
Module: Start & Onboarding Handlers (Dual Product Ecosystem with Back Navigation)
==========================================================
"""

from html import escape
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.handlers.wallpaper import language_for, start_wallpaper_from_start, text_for
from app.bot.states.wallpaper import WallpaperStates
from app.config import get_settings
from app.database import async_session_maker
from app.database.models import FileKind, Language, Menu, MenuStatus, ShareLink, WallpaperOrder
from app.database.repositories import CustomerRepository, MenuRepository

router = Router(name="start")


@router.message(F.text.startswith("/start share_"))
async def open_shared_gift(message: Message) -> None:
    token = (message.text or "").removeprefix("/start share_").strip()
    if len(token) != 32 or not all(c.isalnum() or c in "-_" for c in token):
        await message.answer("Посилання на подарунок недійсне.")
        return
    async with async_session_maker() as session:
        link = await session.get(ShareLink, token)
        if link is None:
            await message.answer("Посилання на подарунок недійсне.")
            return
        path = None
        attachments: list[Path] = []
        if link.kind == "menu":
            menu = await session.get(Menu, int(link.reference_id))
            if menu and menu.is_paid and menu.status not in (MenuStatus.FAILED, MenuStatus.QUEUED):
                await session.refresh(menu, ["files"])
                path = next((Path(file.path) for file in menu.files if file.kind == FileKind.PREVIEW_OUTSIDE), None)
                attachments = [Path(file.path) for file in menu.files
                               if file.kind in (FileKind.PRINT_PDF, FileKind.RECIPE_SHEET)]
        elif link.kind == "gift":
            from app.miniapp.api import _read_job
            try:
                job = _read_job(link.owner_telegram_id, link.reference_id)
                if job["status"] == "ready":
                    if job.get("order_id"):
                        order = await session.get(WallpaperOrder, job["order_id"])
                        if order and order.paid:
                            mobile = Path(order.mobile_path)
                            path = mobile.with_name(f"preview_{mobile.stem}.jpg")
                            attachments = [mobile, Path(order.desktop_path)]
                    elif job.get("free"):
                        mobile = get_settings().generated_dir / "wallpapers" / str(link.owner_telegram_id) / link.reference_id / f"manifestation_{link.owner_telegram_id}_mobile.png"
                        path = mobile.with_name(f"preview_{mobile.stem}.jpg")
                        attachments = [mobile, mobile.with_name(mobile.name.replace("_mobile.png", "_desktop.png"))]
            except Exception:
                path = None
        elif link.kind == "wallpaper":
            order = await session.get(WallpaperOrder, int(link.reference_id))
            if order and order.paid and order.telegram_user_id == link.owner_telegram_id:
                mobile = Path(order.mobile_path)
                path = mobile.with_name(f"preview_{mobile.stem}.jpg")
                attachments = [mobile, Path(order.desktop_path)]
    if not path or not path.is_file():
        await message.answer("Подарунок поки недоступний.")
        return
    url = get_settings().miniapp_url
    keyboard = (InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Створити власний подарунок ✦", web_app=WebAppInfo(url=url))]]) if url else None)
    await message.answer_photo(FSInputFile(str(path)),
                               caption="Для вас підготували особливий подарунок 💛", reply_markup=keyboard)
    for attachment in attachments:
        if attachment.is_file():
            try:
                await message.answer_document(FSInputFile(str(attachment)))
            except Exception:
                # Keep the share link valid; Telegram may reject an unusually large file.
                import logging
                logging.getLogger(__name__).exception("Could not send shared file %s", attachment)


def get_phone_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    text = text_for(lang, "📱 Поділитися номером", "📱 Поделиться номером", "📱 Share phone number")
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=text, request_contact=True)],
            [KeyboardButton(text=text_for(lang, "🏠 Головне меню", "🏠 Главное меню", "🏠 Main menu"))]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_products_menu_keyboard(user_id: int | None = None, lang: str = "uk") -> InlineKeyboardMarkup:
    """Головне меню вибору продуктів екосистеми."""
    buttons = [
        [InlineKeyboardButton(text=text_for(lang, "🍷 Гастрономічний подарунок",
            "🍷 Гастрономический подарок", "🍷 A food gift"), callback_data="prod_food_porn")],
        [InlineKeyboardButton(text=text_for(lang,
            "🎁 Подарунок для близької людини", "🎁 Подарок близкому человеку",
            "🎁 A gift for someone special"), callback_data="prod_manifestation")],
    ]
    buttons.append([InlineKeyboardButton(text=text_for(lang, "🌐 Мова", "🌐 Язык", "🌐 Language"),
                                         callback_data="choose_language")])
    if user_id in get_settings().admin_telegram_ids:
        buttons.append([InlineKeyboardButton(text="👑 Панель керування (Адмін)", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def language_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=label, callback_data=f"ui_lang:{code}")]
        for code, label in (("uk", "🇺🇦 Українська"), ("ru", "🇷🇺 Русский"), ("en", "🇬🇧 English"))])


async def preferred_language(user: object, state: FSMContext) -> str:
    current = (await state.get_data()).get("ui_lang")
    if current in {"uk", "ru", "en"}:
        return current
    async with async_session_maker() as session:
        customer = await CustomerRepository(session).by_telegram_id(user.id)
    return customer.language.value if customer else language_for(user)


@router.message(F.text.in_({"🏠 Головне меню", "🏠 Главное меню", "🏠 Main menu",
                           "/start", "⬅️ Назад до продуктів"}))
async def cmd_start(message: Message, state: FSMContext) -> None:
    selected = (await state.get_data()).get("lang_selected", False)
    lang = await preferred_language(message.from_user, state)
    await state.clear()
    await state.update_data(ui_lang=lang, lang_selected=selected)
    name = escape((message.from_user.first_name or "") if message.from_user else "")
    miniapp_url = get_settings().miniapp_url
    if miniapp_url:
        await message.answer(text_for(lang,
            f"Привіт, {name}! 💛 Відкрийте майстерню подарунків: фото, бажання й замовлення тепер в одному місці.",
            f"Привет, {name}! 💛 Откройте мастерскую подарков: фото, желания и заказы теперь в одном месте.",
            f"Hi, {name}! 💛 Open your gift studio to create and track everything in one place."),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text=text_for(lang, "✨ Відкрити майстерню", "✨ Открыть мастерскую", "✨ Open the studio"),
                web_app=WebAppInfo(url=miniapp_url),
            )]]))
        return
    await message.answer(
        text_for(lang,
            f"Привіт, {name}! 💛 Допоможу візуалізувати п’ять ваших бажань у подарунку для близької людини. Потрібні фото та 5 цілей. Або оберіть гастрономічний сет.",
            f"Привет, {name}! 💛 Помогу визуализировать пять ваших желаний в подарке для близкого человека. Нужны фото и 5 целей. Или выберите гастрономический сет.",
            f"Hi, {name}! 💛 Let's visualize five of your wishes as a gift for someone special. Send photos and 5 goals, or choose a food menu."),
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(text_for(lang, "Чим порадуємо сьогодні?", "Чем порадуем сегодня?", "What shall we create today?"),
                         reply_markup=get_products_menu_keyboard(message.from_user.id, lang))


@router.callback_query(F.data == "back_to_products")
async def callback_back_to_products(callback: CallbackQuery, state: FSMContext) -> None:
    selected = (await state.get_data()).get("lang_selected", False)
    lang = await preferred_language(callback.from_user, state)
    await state.clear()
    await state.update_data(ui_lang=lang, lang_selected=selected)
    text = text_for(lang, "Оберіть подарунок або меню:", "Выберите подарок или меню:", "Choose a gift or a menu:")
    try:
        await callback.message.edit_text(text, reply_markup=get_products_menu_keyboard(callback.from_user.id, lang), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=get_products_menu_keyboard(callback.from_user.id, lang), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "choose_language")
async def choose_language(callback: CallbackQuery) -> None:
    await callback.message.answer("Мова / Язык / Language:", reply_markup=language_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("ui_lang:"))
async def set_ui_language(callback: CallbackQuery, state: FSMContext) -> None:
    lang = (callback.data or "").removeprefix("ui_lang:")
    if lang not in {"uk", "ru", "en"}:
        await callback.answer("Unknown language", show_alert=True)
        return
    await state.update_data(ui_lang=lang, lang=lang, lang_selected=True)
    async with async_session_maker() as session:
        customer = await CustomerRepository(session).by_telegram_id(callback.from_user.id)
        if customer:
            customer.language = Language(lang)
            await session.commit()
    await callback.message.answer(text_for(lang,
        "Готово 💛 Оберіть подарунок:", "Готово 💛 Выберите подарок:",
        "All set 💛 Choose a gift:"), reply_markup=get_products_menu_keyboard(callback.from_user.id, lang))
    await callback.answer()


@router.message(F.contact)
async def receive_contact(message: Message, state: FSMContext, session_factory: async_sessionmaker[AsyncSession] = None) -> None:
    if message.from_user is None or message.contact is None:
        return
    if message.contact.user_id != message.from_user.id:
        await message.answer("Пожалуйста, поделитесь своим контактом через кнопку.")
        return

    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone

    is_ukrainian_number = phone.startswith("+380")
    currency = get_settings().currency
    lang = "uk" if phone.startswith("+380") else "ru" if phone.startswith("+7") else "en"
    chosen = (await state.get_data()).get("ui_lang")
    if (await state.get_data()).get("lang_selected") and chosen in {"uk", "ru", "en"}:
        lang = chosen

    async with async_session_maker() as session:
        customer_repo = CustomerRepository(session)
        await customer_repo.register(
            telegram_user_id=message.from_user.id,
            phone=phone,
            name=message.from_user.full_name or "Client",
            language=Language(lang),
            country="Ukraine" if is_ukrainian_number else "International",
            city="Not provided",
        )

    await state.update_data(phone=phone, currency=currency, lang=lang, ui_lang=lang)

    if (await state.get_data()).get("pending_food"):
        await state.update_data(pending_food=False)
        await message.answer(text_for(lang, "Дякую! Створімо гастрономічний подарунок 🍷",
            "Спасибо! Создадим гастрономический подарок 🍷", "Thank you! Let's make a food gift 🍷"),
            reply_markup=ReplyKeyboardRemove())
        await _send_food_start(message, state)
        return

    text = text_for(lang, "Мову встановлено 💛", "Язык установлен 💛", "Language selected 💛")
    await message.answer(text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await message.answer(text_for(lang, "Оберіть подарунок:", "Выберите подарок:", "Choose a gift:"),
                         reply_markup=get_products_menu_keyboard(message.from_user.id, lang))


@router.callback_query(F.data == "prod_manifestation")
async def start_manifestation_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await start_wallpaper_from_start(
        callback.message, state, user_id=callback.from_user.id,
        lang=await preferred_language(callback.from_user, state),
    )
    await callback.answer()


@router.message(WallpaperStates.waiting_for_photo, F.text == "⬅️ Назад до меню")
async def cancel_wallpaper_flow(message: Message, state: FSMContext) -> None:
    selected = (await state.get_data()).get("lang_selected", False)
    lang = await preferred_language(message.from_user, state)
    await state.clear()
    await state.update_data(ui_lang=lang, lang_selected=selected)
    await message.answer(text_for(lang, "Головне меню 💛", "Главное меню 💛", "Main menu 💛"),
                         reply_markup=get_products_menu_keyboard(message.from_user.id, lang))


@router.callback_query(F.data == "prod_food_porn")
async def start_food_porn_flow(callback: CallbackQuery, state: FSMContext) -> None:
    async with async_session_maker() as session:
        customer_repo = CustomerRepository(session)
        customer = await customer_repo.by_telegram_id(callback.from_user.id)
    if customer is None:
        await state.update_data(pending_food=True)
        lang = await preferred_language(callback.from_user, state)
        await callback.message.answer(
            text_for(lang, "Для замовлення меню потрібен ваш контакт. Поділіться ним, будь ласка.",
                     "Для заказа меню нужен ваш контакт. Поделитесь им, пожалуйста.",
                     "Please share your contact to order a food gift."),
            reply_markup=get_phone_keyboard(lang),
        )
        await callback.answer()
        return
    await _send_food_start(callback.message, state, customer=customer)
    await callback.answer()


async def _send_food_start(message: Message, state: FSMContext, customer=None) -> None:
    if customer is None:
        async with async_session_maker() as session:
            customer = await CustomerRepository(session).by_telegram_id(message.from_user.id)
    if customer is None:
        await message.answer("Не вдалося знайти ваш профіль. Спробуйте /start ще раз.")
        return
    async with async_session_maker() as session:
        menu = await MenuRepository(session).create(customer)
    await state.update_data(menu_id=menu.id)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏠 Головне меню")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    text = text_for(customer.language.value,
        "🍷 <b>Гастрономічний подарунок</b>\n\nНапишіть назву першої страви:",
        "🍷 <b>Гастрономический подарок</b>\n\nНапишите название первого блюда:",
        "🍷 <b>A food gift</b>\n\nType the first dish:")
    await message.answer(text, parse_mode="HTML", reply_markup=kb)
