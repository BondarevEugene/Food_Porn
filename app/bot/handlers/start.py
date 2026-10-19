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

from app.bot.handlers.menu import begin_menu_setup
from app.bot.handlers.wallpaper import language_for, start_wallpaper_from_start, text_for
from app.bot.states.wallpaper import WallpaperStates
from app.config import get_settings
from app.database import async_session_maker
from app.database.models import FileKind, Language, Menu, MenuStatus, ShareLink, WallpaperOrder
from app.database.repositories import CustomerRepository
from app.services.admin_access import has_admin_access

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
                path = next(
                    (
                        Path(file.path)
                        for file in menu.files
                        if file.kind == FileKind.PREVIEW_OUTSIDE
                    ),
                    None,
                )
                attachments = [
                    Path(file.path)
                    for file in menu.files
                    if file.kind in (FileKind.PRINT_PDF, FileKind.RECIPE_SHEET)
                ]
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
                        mobile = (
                            get_settings().generated_dir
                            / "wallpapers"
                            / str(link.owner_telegram_id)
                            / link.reference_id
                            / f"manifestation_{link.owner_telegram_id}_mobile.png"
                        )
                        path = mobile.with_name(f"preview_{mobile.stem}.jpg")
                        attachments = [
                            mobile,
                            mobile.with_name(mobile.name.replace("_mobile.png", "_desktop.png")),
                        ]
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
    if url:
        await message.answer(
            "Для вас підготували дещо особливе ✦ Відкрийте конверт — усередині подарунок.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✦ Відкрити подарунок",
                            web_app=WebAppInfo(url=f"{url.rstrip('/')}/open/{token}"),
                        )
                    ]
                ]
            ),
        )
        return
    keyboard = (
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Створити власний подарунок ✦", web_app=WebAppInfo(url=url)
                    )
                ]
            ]
        )
        if url
        else None
    )
    await message.answer_photo(
        FSInputFile(str(path)),
        caption="Для вас підготували особливий подарунок 💛",
        reply_markup=keyboard,
    )
    for attachment in attachments:
        if attachment.is_file():
            try:
                await message.answer_document(FSInputFile(str(attachment)))
            except Exception:
                # Keep the share link valid; Telegram may reject an unusually large file.
                import logging

                logging.getLogger(__name__).exception("Could not send shared file %s", attachment)


@router.message(F.text.startswith("/start ref_"))
async def open_referral(message: Message, state: FSMContext) -> None:
    """Keep referral starts usable without letting them bypass onboarding."""
    inviter = (message.text or "").removeprefix("/start ref_").strip()
    if inviter.isdigit() and message.from_user and inviter != str(message.from_user.id):
        await state.update_data(referrer_telegram_id=int(inviter))
    await message.answer(
        "Вітаємо 💛 / Добро пожаловать 💛 / Welcome 💛\n\nМова / Язык / Language:",
        reply_markup=language_menu(),
    )


def get_phone_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    text = text_for(lang, "📱 Поділитися номером", "📱 Поделиться номером", "📱 Share phone number")
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=text, request_contact=True)],
            [
                KeyboardButton(
                    text=text_for(lang, "🏠 Головне меню", "🏠 Главное меню", "🏠 Main menu")
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_products_menu_keyboard(
    user_id: int | None = None, lang: str = "uk", *, is_admin: bool = False
) -> InlineKeyboardMarkup:
    """Головне меню вибору продуктів екосистеми."""
    buttons = [
        [
            InlineKeyboardButton(
                text=text_for(lang, "🍽 Створити меню", "🍽 Создать меню", "🍽 Create a menu"),
                callback_data="prod_food_porn",
            )
        ],
        [
            InlineKeyboardButton(
                text=text_for(
                    lang,
                    "📱 Створити карту бажань на заставку",
                    "📱 Создать карту желаний на заставку",
                    "📱 Create a vision-board wallpaper",
                ),
                callback_data="prod_manifestation",
            )
        ],
    ]
    buttons.extend([
        [
            InlineKeyboardButton(text=text_for(lang, "📦 Мої замовлення", "📦 Мои заказы", "📦 My orders"), callback_data="home_orders"),
            InlineKeyboardButton(text=text_for(lang, "🎁 Запросити друга", "🎁 Пригласить друга", "🎁 Invite a friend"), callback_data="home_referral"),
        ],
        [
            InlineKeyboardButton(text=text_for(lang, "📖 Інструкція", "📖 Инструкция", "📖 How it works"), callback_data="home_instruction"),
            InlineKeyboardButton(text="FAQ", callback_data="home_faq"),
        ],
        [
            InlineKeyboardButton(text=text_for(lang, "💬 Підтримка", "💬 Поддержка", "💬 Support"), callback_data="home_support"),
            InlineKeyboardButton(text=text_for(lang, "🌐 Мова", "🌐 Язык", "🌐 Language"), callback_data="choose_language"),
        ],
    ])
    if is_admin or user_id in get_settings().admin_telegram_ids:
        buttons.append(
            [InlineKeyboardButton(text="👑 Панель керування (Адмін)", callback_data="admin_home")]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_user_products_menu_keyboard(user: object, lang: str = "uk") -> InlineKeyboardMarkup:
    allowed = await has_admin_access(
        user.id, getattr(user, "username", None), get_settings(), async_session_maker
    )
    return get_products_menu_keyboard(user.id, lang, is_admin=allowed)


def language_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"ui_lang:{code}")]
            for code, label in (("uk", "🇺🇦 Українська"), ("ru", "🇷🇺 Русский"), ("en", "🇬🇧 English"))
        ]
    )


async def preferred_language(user: object, state: FSMContext) -> str:
    current = (await state.get_data()).get("ui_lang")
    if current in {"uk", "ru", "en"}:
        return current
    async with async_session_maker() as session:
        customer = await CustomerRepository(session).by_telegram_id(user.id)
    return customer.language.value if customer else language_for(user)


@router.message(
    F.text.in_(
        {"🏠 Головне меню", "🏠 Главное меню", "🏠 Main menu", "/start", "⬅️ Назад до продуктів"}
    )
)
async def cmd_start(message: Message, state: FSMContext) -> None:
    if (getattr(message, "text", "") or "").strip() == "/start":
        await state.clear()
        await message.answer(
            "Вітаємо 💛 / Добро пожаловать 💛 / Welcome 💛\n\nМова / Язык / Language:",
            reply_markup=language_menu(),
        )
        return
    selected = (await state.get_data()).get("lang_selected", False)
    lang = await preferred_language(message.from_user, state)
    await state.clear()
    await state.update_data(ui_lang=lang, lang_selected=selected)
    name = escape((message.from_user.first_name or "") if message.from_user else "")
    await message.answer(
        text_for(
            lang,
            f"Привіт, {name}! 💛 Допоможу візуалізувати п’ять ваших бажань у подарунку для близької людини. Потрібні фото та 5 цілей. Або оберіть гастрономічний сет.",
            f"Привет, {name}! 💛 Помогу визуализировать пять ваших желаний в подарке для близкого человека. Нужны фото и 5 целей. Или выберите гастрономический сет.",
            f"Hi, {name}! 💛 Let's visualize five of your wishes as a gift for someone special. Send photos and 5 goals, or choose a food menu.",
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        text_for(
            lang, "Чим порадуємо сьогодні?", "Чем порадуем сегодня?", "What shall we create today?"
        ),
        reply_markup=await get_user_products_menu_keyboard(message.from_user, lang),
    )


@router.callback_query(F.data == "back_to_products")
async def callback_back_to_products(callback: CallbackQuery, state: FSMContext) -> None:
    selected = (await state.get_data()).get("lang_selected", False)
    lang = await preferred_language(callback.from_user, state)
    await state.clear()
    await state.update_data(ui_lang=lang, lang_selected=selected)
    text = text_for(
        lang,
        "Оберіть подарунок або меню:",
        "Выберите подарок или меню:",
        "Choose a gift or a menu:",
    )
    try:
        await callback.message.edit_text(
            text,
            reply_markup=await get_user_products_menu_keyboard(callback.from_user, lang),
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=await get_user_products_menu_keyboard(callback.from_user, lang),
            parse_mode="HTML",
        )
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
    await callback.message.answer(
        text_for(
            lang,
            "Готово 💛 Оберіть подарунок:",
            "Готово 💛 Выберите подарок:",
            "All set 💛 Choose a gift:",
        ),
        reply_markup=await get_user_products_menu_keyboard(callback.from_user, lang),
    )
    await callback.answer()


@router.callback_query(F.data == "home_instruction")
async def show_instruction(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await preferred_language(callback.from_user, state)
    await callback.message.answer(
        text_for(
            lang,
            "📖 <b>Як це працює</b>\n\n1. Оберіть продукт.\n2. Додайте фото й побажання або список страв.\n3. Перевірте форму та сплатіть.\n4. Отримайте готові електронні файли в Telegram.",
            "📖 <b>Как это работает</b>\n\n1. Выберите продукт.\n2. Добавьте фото и пожелания или список блюд.\n3. Проверьте форму и оплатите.\n4. Получите готовые электронные файлы в Telegram.",
            "📖 <b>How it works</b>\n\n1. Choose a product.\n2. Add photos and wishes or dishes.\n3. Review the form and pay.\n4. Receive the digital files in Telegram.",
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В начало", callback_data="back_to_products")]
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "home_faq")
async def show_faq(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await preferred_language(callback.from_user, state)
    await callback.message.answer(
        text_for(
            lang,
            "❓ <b>Часті питання</b>\n\n• Меню: два фото, список страв, рецепти та PDF.\n• Карта бажань: фото, цілі та заставки для телефону й комп’ютера.\n• До оплати можна повертатися назад і змінювати дані.",
            "❓ <b>Частые вопросы</b>\n\n• Меню: два фото, список блюд, рецепты и PDF.\n• Карта желаний: фото, цели и заставки для телефона и компьютера.\n• До оплаты можно вернуться назад и изменить данные.",
            "❓ <b>FAQ</b>\n\n• Menu: two photos, dishes, recipes and PDF.\n• Vision board: photos, goals, mobile and desktop wallpapers.\n• You can go back and edit everything before payment.",
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В начало", callback_data="back_to_products")]
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "home_support")
async def show_support(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await preferred_language(callback.from_user, state)
    await callback.message.answer(
        text_for(
            lang,
            "💬 Опишіть проблему одним повідомленням і додайте скріншот. Адміністратор побачить ваш Telegram ID:",
            "💬 Опишите проблему одним сообщением и приложите скриншот. Администратор увидит ваш Telegram ID:",
            "💬 Describe the issue in one message and attach a screenshot. The administrator will see your Telegram ID:",
        ) + f" <code>{callback.from_user.id}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В начало", callback_data="back_to_products")]
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "home_referral")
async def show_referral(callback: CallbackQuery, state: FSMContext) -> None:
    lang = await preferred_language(callback.from_user, state)
    bot = await callback.bot.get_me()
    link = f"https://t.me/{bot.username}?start=ref_{callback.from_user.id}"
    await callback.message.answer(
        text_for(
            lang,
            "🎁 Поділіться посиланням із другом:",
            "🎁 Поделитесь ссылкой с другом:",
            "🎁 Share this link with a friend:",
        ) + f"\n<code>{link}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В начало", callback_data="back_to_products")]
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(F.contact)
async def receive_contact(
    message: Message, state: FSMContext, session_factory: async_sessionmaker[AsyncSession] = None
) -> None:
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
        await message.answer(
            text_for(
                lang,
                "Дякую! Створімо гастрономічний подарунок 🍷",
                "Спасибо! Создадим гастрономический подарок 🍷",
                "Thank you! Let's make a food gift 🍷",
            ),
            reply_markup=ReplyKeyboardRemove(),
        )
        await _send_food_start(message, state)
        return

    text = text_for(lang, "Мову встановлено 💛", "Язык установлен 💛", "Language selected 💛")
    await message.answer(text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        text_for(lang, "Оберіть подарунок:", "Выберите подарок:", "Choose a gift:"),
        reply_markup=await get_user_products_menu_keyboard(message.from_user, lang),
    )


@router.callback_query(F.data == "prod_manifestation")
async def start_manifestation_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await start_wallpaper_from_start(
        callback.message,
        state,
        user_id=callback.from_user.id,
        lang=await preferred_language(callback.from_user, state),
    )
    await callback.answer()


@router.message(WallpaperStates.waiting_for_photo, F.text == "⬅️ Назад до меню")
async def cancel_wallpaper_flow(message: Message, state: FSMContext) -> None:
    selected = (await state.get_data()).get("lang_selected", False)
    lang = await preferred_language(message.from_user, state)
    await state.clear()
    await state.update_data(ui_lang=lang, lang_selected=selected)
    await message.answer(
        text_for(lang, "Головне меню 💛", "Главное меню 💛", "Main menu 💛"),
        reply_markup=await get_user_products_menu_keyboard(message.from_user, lang),
    )


@router.callback_query(F.data == "prod_food_porn")
async def start_food_porn_flow(callback: CallbackQuery, state: FSMContext) -> None:
    async with async_session_maker() as session:
        customer_repo = CustomerRepository(session)
        customer = await customer_repo.by_telegram_id(callback.from_user.id)
    if customer is None:
        await state.update_data(pending_food=True)
        lang = await preferred_language(callback.from_user, state)
        await callback.message.answer(
            text_for(
                lang,
                "Для замовлення меню потрібен ваш контакт. Поділіться ним, будь ласка.",
                "Для заказа меню нужен ваш контакт. Поделитесь им, пожалуйста.",
                "Please share your contact to order a food gift.",
            ),
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
    await begin_menu_setup(message, state, customer.language.value)
