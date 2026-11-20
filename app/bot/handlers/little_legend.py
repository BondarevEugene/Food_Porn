"""Entry point for Little Legend as Food_Porn's third product."""
import logging
from urllib.parse import urlsplit, urlunsplit

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import select

from app.bot.handlers.little_legend_checkpoint import router as checkpoint_router
from app.bot.handlers.little_legend_guided import router as guided_router
from app.bot.handlers.little_legend_outline import router as outline_router
from app.bot.handlers.little_legend_palettes import router as palette_router
from app.bot.handlers.wallpaper import language_for, text_for
from app.config import get_settings
from app.database.session import async_session_maker
from app.little_legend.aiogram_pdf_sender import AiogramPDFSender
from app.little_legend.art_storage_config import configured_generated_art_store
from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.commercial_catalog import crm_book_catalog
from app.little_legend.owned_production import load_owned_production
from app.little_legend.pdf_storage_config import configured_private_pdf_store
from app.little_legend.readiness_messages import readiness_message
from app.little_legend.release_manifest_store import get_release_manifest
from app.little_legend.release_orchestrator import prepare_owned_release, send_owned_release
from app.little_legend.router import stories

logger = logging.getLogger(__name__)

router = Router(name="little_legend")
router.include_router(palette_router)
router.include_router(checkpoint_router)
router.include_router(outline_router)
router.include_router(guided_router)


def little_legend_studio_url(configured_url: str) -> str | None:
    """Convert an existing MINIAPP_URL into the studio URL."""
    try:
        parsed = urlsplit(configured_url.strip())
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    path = parsed.path.rstrip("/")
    if path.endswith("/miniapp"):
        path = path.removesuffix("/miniapp")
    return urlunsplit(("https", parsed.netloc, path + "/little-legend", "", ""))



@router.callback_query(F.data == "prod_little_legend")
async def open_little_legend(callback: CallbackQuery) -> None:
    lang = language_for(callback.from_user)
    studio_url = little_legend_studio_url(get_settings().miniapp_url)
    buttons = [[InlineKeyboardButton(
        text=text_for(lang, "✨ Створити книгу", "✨ Создать книгу", "✨ Create a book"),
        callback_data="ll_choose_mode",
    )]]
    if studio_url:
        buttons.append([InlineKeyboardButton(
            text=text_for(lang, "🎨 Редактор книги", "🎨 Редактор книги", "🎨 Book editor"),
            web_app=WebAppInfo(url=studio_url),
        )])
    buttons.append([InlineKeyboardButton(
        text=text_for(lang, "💎 Формати й ціни", "💎 Форматы и цены", "💎 Editions & prices"),
        callback_data="ll_catalog",
    )])
    buttons.append([InlineKeyboardButton(
        text=text_for(lang, "📚 Мої книги", "📚 Мои книги", "📚 My books"),
        callback_data="ll_books",
    )])
    buttons.append([InlineKeyboardButton(
        text=text_for(lang, "⬅️ До продуктів", "⬅️ К продуктам", "⬅️ Back to products"),
        callback_data="back_to_products",
    )])
    message = text_for(
        lang,
        "📚 <b>Little Legend</b> — персональна книга про вашу дитину. Створіть сюжет, героїв та 12 сцен.",
        "📚 <b>Little Legend</b> — персональная книга о вашем ребёнке. Создайте сюжет, героев и 12 сцен.",
        "📚 <b>Little Legend</b> — a personal book starring your child. Design the story, characters and 12 scenes.",
    )
    if not studio_url:
        message += "\n\n" + text_for(
            lang, "Студія стане доступною після налаштування MINIAPP_URL (HTTPS).",
            "Студия станет доступна после настройки MINIAPP_URL (HTTPS).",
            "The studio will open once MINIAPP_URL (HTTPS) is configured.",
        )
    await callback.message.answer(message, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "ll_choose_mode")
async def choose_little_legend_mode(callback: CallbackQuery) -> None:
    """One clear decision per screen; preserve the existing editor route."""
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Open this in a private chat", show_alert=True)
        return
    lang = language_for(callback.from_user)
    options = [
        ("director", ("✍️ Моя історія", "✍️ Моя история", "✍️ My story")),
        ("classic", ("🏰 Я — герой казки", "🏰 Я — герой сказки", "🏰 Classic hero")),
        ("brief", ("✨ Казка за моєю ідеєю", "✨ Сказка по моей идее", "✨ My story idea")),
    ]
    buttons = [
        [InlineKeyboardButton(text=text_for(lang, *labels), callback_data=f"ll_mode:{mode}")]
        for mode, labels in options
    ]
    buttons.append([InlineKeyboardButton(
        text=text_for(lang, "⬅️ Назад", "⬅️ Назад", "⬅️ Back"),
        callback_data="prod_little_legend",
    )])
    await callback.message.answer(
        text_for(lang,
                 "📖 Крок 1/5 · Як створимо вашу книгу?",
                 "📖 Шаг 1/5 · Как создадим вашу книгу?",
                 "📖 Step 1/5 · How shall we create your book?"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data == "ll_mode:director")
async def show_little_legend_mode(callback: CallbackQuery) -> None:
    """Explain mode readiness without pretending an unsupported editor is live."""
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Open this in a private chat", show_alert=True)
        return
    lang = language_for(callback.from_user)
    mode = (callback.data or "").removeprefix("ll_mode:")
    if mode not in {"director", "classic", "brief"}:
        await callback.answer("Unknown mode", show_alert=True)
        return
    studio_url = little_legend_studio_url(get_settings().miniapp_url)
    if mode == "director":
        message = text_for(
            lang,
            "✍️ Моя історія: детально створюйте героїв, події та сцени.",
            "✍️ Моя история: подробно создавайте героев, события и сцены.",
            "✍️ My story: design characters, events and scenes in detail.",
        )
    elif mode == "classic":
        message = text_for(
            lang,
            "🏰 Адаптація класики: перевірка прав на твір та новий редактор ще готуються.",
            "🏰 Адаптация классики: проверка прав на произведение и новый редактор ещё готовятся.",
            "🏰 Classic adaptation: rights review and the new editor are being prepared.",
        )
    else:
        message = text_for(
            lang,
            "✨ Короткий бриф: сценарний рушій додано, покроковий редактор ще готується.",
            "✨ Короткий бриф: сценарный движок добавлен, пошаговый редактор ещё готовится.",
            "✨ Short brief: story planning is available internally; the guided editor is coming.",
        )
    buttons = []
    if mode == "director" and studio_url:
        buttons.append([InlineKeyboardButton(
            text=text_for(lang, "📖 Відкрити редактор", "📖 Открыть редактор", "📖 Open editor"),
            web_app=WebAppInfo(url=studio_url),
        )])
    buttons.append([InlineKeyboardButton(
        text=text_for(lang, "⬅️ Обрати інший режим", "⬅️ Выбрать другой режим", "⬅️ Choose another mode"),
        callback_data="ll_choose_mode",
    )])
    await callback.message.answer(
        message, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data == "ll_books")
async def list_my_little_legend_books(callback: CallbackQuery) -> None:
    """Telegram-native owner-scoped list; no child profile or manuscript leaks."""
    owner_id = callback.from_user.id
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(stories.c.id, stories.c.title).where(
                stories.c.owner_id == owner_id,
            ).order_by(stories.c.id.desc()).limit(10)
        )).all()
    lang = language_for(callback.from_user)
    buttons = [
        [InlineKeyboardButton(
            text=f"📖 #{story_id} · {title[:36]}",
            callback_data=f"ll_book:{story_id}",
        )]
        for story_id, title in rows
    ]
    buttons.append([InlineKeyboardButton(
        text=text_for(lang, "⬅️ До продуктів", "⬅️ К продуктам", "⬅️ Back to products"),
        callback_data="back_to_products",
    )])
    message = text_for(
        lang, "📚 Ваші книги", "📚 Ваши книги", "📚 Your books",
    ) if rows else text_for(
        lang, "Поки немає книг.", "Пока нет книг.", "No books yet.",
    )
    await callback.message.answer(
        message, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_book:"))
async def show_little_legend_book(callback: CallbackQuery) -> None:
    """Never reveal whether a foreign story ID exists."""
    lang = language_for(callback.from_user)
    try:
        story_id = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Invalid book", show_alert=True)
        return
    if story_id <= 0:
        await callback.answer("Invalid book", show_alert=True)
        return
    owner_id = callback.from_user.id
    async with async_session_maker() as session:
        owned = (await session.execute(select(stories.c.id).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ))).scalar_one_or_none()
    if owned is None:
        await callback.answer("Book not found", show_alert=True)
        return
    manifest = await get_release_manifest(owner_id=owner_id, story_id=story_id)
    status = manifest.status if manifest else None
    status_labels = {
        None: ("⏳ У роботі", "⏳ В работе", "⏳ In production"),
        DeliveryStatus.READY: ("📦 Готова до видачі", "📦 Готова к выдаче", "📦 Ready for delivery"),
        DeliveryStatus.SENDING: ("⏳ Відправлення", "⏳ Отправка", "⏳ Sending"),
        DeliveryStatus.SENT: ("✅ Надіслано", "✅ Отправлено", "✅ Delivered"),
        DeliveryStatus.UNCERTAIN: ("⚠️ Потрібна перевірка", "⚠️ Нужна проверка", "⚠️ Needs review"),
    }
    status_text = text_for(lang, *status_labels[status])
    readiness_text = ""
    ready_for_assembly = False
    if status is None:
        try:
            production = await load_owned_production(
                owner_id=owner_id, story_id=story_id,
            )
            readiness = production.readiness()
            ready_for_assembly = readiness.ready_for_export
            readiness_text = readiness_message(
                readiness, language=lang,
            )
        except PermissionError:
            readiness_text = text_for(
                lang, "📖 Завершіть створення історії в студії.",
                "📖 Завершите создание истории в студии.",
                "📖 Complete the story in the studio.",
            )
        except Exception:
            logger.exception("Little Legend readiness lookup failed")
            readiness_text = text_for(
                lang, "⚠️ Статус тимчасово недоступний.",
                "⚠️ Статус временно недоступен.",
                "⚠️ Status is temporarily unavailable.",
            )
    buttons = []
    if callback.message.chat.type == "private":
        buttons.append([InlineKeyboardButton(
            text="📊 Производство книги",
            callback_data=f"ll_checkpoint:{story_id}",
        )])
    if status is None and callback.message.chat.type == "private":
        buttons.append([InlineKeyboardButton(
            text="📖 Посмотреть и утвердить план",
            callback_data=f"ll_outline:{story_id}",
        )])
    if ready_for_assembly and callback.message.chat.type == "private":
        buttons.append([InlineKeyboardButton(
            text=text_for(
                lang, "📘 Підготувати книгу", "📘 Подготовить книгу",
                "📘 Prepare book",
            ),
            callback_data=f"ll_prepare:{story_id}",
        )])
    if status == DeliveryStatus.READY and callback.message.chat.type == "private":
        buttons.append([InlineKeyboardButton(
            text=text_for(lang, "📥 Отримати PDF", "📥 Получить PDF", "📥 Get PDF"),
            callback_data=f"ll_send:{story_id}",
        )])
    if status is None and callback.message.chat.type == "private":
        buttons.append([InlineKeyboardButton(
            text=text_for(lang, "🎨 Оформлення книги", "🎨 Оформление книги",
                          "🎨 Book colors"),
            callback_data=f"ll_palette:{story_id}",
        )])
    buttons.append([
            InlineKeyboardButton(
                text=text_for(lang, "⬅️ Мої книги", "⬅️ Мои книги", "⬅️ My books"),
                callback_data="ll_books",
            ),
        ])
    await callback.message.answer(
        f"📖 #{story_id} — {status_text}" + (f"\n\n{readiness_text}" if readiness_text else ""),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_send:"))
async def send_little_legend_book(callback: CallbackQuery) -> None:
    """One explicit owner-authorized send; no automatic retries on ambiguity."""
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Open this in a private chat", show_alert=True)
        return
    try:
        story_id = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Invalid book", show_alert=True)
        return
    if story_id <= 0:
        await callback.answer("Invalid book", show_alert=True)
        return
    owner_id = callback.from_user.id
    if callback.message.chat.id != owner_id:
        await callback.answer("Open your own private chat", show_alert=True)
        return
    async with async_session_maker() as session:
        owned = (await session.execute(select(stories.c.id).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ))).scalar_one_or_none()
    if owned is None:
        await callback.answer("Book not found", show_alert=True)
        return
    manifest = await get_release_manifest(owner_id=owner_id, story_id=story_id)
    if manifest is None or manifest.status != DeliveryStatus.READY:
        await callback.answer("Book is not ready for delivery", show_alert=True)
        return
    try:
        pdf_store = configured_private_pdf_store()
    except ValueError:
        await callback.answer("Delivery storage is not configured", show_alert=True)
        return
    await callback.answer()
    try:
        outcome = await send_owned_release(
            owner_id=owner_id, story_id=story_id,
            pdf_store=pdf_store, sender=AiogramPDFSender(callback.bot),
        )
    except PermissionError:
        await callback.message.answer(
            "Delivery is already reserved or needs review. No duplicate was sent.",
        )
        return
    except Exception:
        logger.exception("Little Legend delivery requires reconciliation")
        await callback.message.answer(
            "⚠️ Delivery could not be confirmed. Contact support; do not retry."
        )
        return
    if outcome.status == DeliveryStatus.SENT:
        await callback.message.answer("✅ Your PDF book has been delivered.")
    else:
        await callback.message.answer(
            "⚠️ Delivery result is uncertain. Contact support; do not retry.",
        )


@router.callback_query(F.data.startswith("ll_prepare:"))
async def prepare_little_legend_book(callback: CallbackQuery) -> None:
    """Owner-initiated approved-art assembly; never starts paid generation."""
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Open this in a private chat", show_alert=True)
        return
    try:
        story_id = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Invalid book", show_alert=True)
        return
    owner_id = callback.from_user.id
    if story_id <= 0 or callback.message.chat.id != owner_id:
        await callback.answer("Book not found", show_alert=True)
        return
    async with async_session_maker() as session:
        owned = (await session.execute(select(stories.c.id).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ))).scalar_one_or_none()
    if owned is None:
        await callback.answer("Book not found", show_alert=True)
        return
    try:
        art_store = configured_generated_art_store()
        pdf_store = configured_private_pdf_store()
    except ValueError:
        await callback.answer("Private storage is not configured", show_alert=True)
        return
    await callback.answer()
    try:
        manifest = await prepare_owned_release(
            owner_id=owner_id, story_id=story_id,
            art_store=art_store, pdf_store=pdf_store,
        )
    except (PermissionError, ValueError):
        await callback.message.answer(
            "The book is not ready: approve all chapters and illustrations first."
        )
        return
    except Exception:
        logger.exception("Little Legend book preparation failed")
        await callback.message.answer(
            "⚠️ Book preparation failed. Contact support; no paid generation was started."
        )
        return
    if manifest.status == DeliveryStatus.READY:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="📥 Get PDF", callback_data=f"ll_send:{story_id}",
            ),
        ]])
        await callback.message.answer(
            "📘 Your book is ready for delivery.", reply_markup=keyboard,
        )
    else:
        await callback.message.answer(
            "📘 This book has already entered the delivery workflow."
        )


@router.callback_query(F.data == "ll_catalog")
async def show_little_legend_catalog(callback: CallbackQuery) -> None:
    """Customer catalog, never an unverified checkout link."""
    lang = language_for(callback.from_user)
    try:
        catalog = await crm_book_catalog()
    except ValueError:
        logger.exception("Little Legend catalog configuration invalid")
        await callback.answer("Pricing temporarily unavailable", show_alert=True)
        return
    digital, physical = catalog.offers
    digital_price = (
        f"{digital.price_minor // 100},{digital.price_minor % 100:02d} ₴"
        if digital.price_minor is not None else "—"
    )
    physical_price = (
        f"{physical.price_minor // 100},{physical.price_minor % 100:02d} ₴"
        if physical.price_minor is not None else "—"
    )
    heading = text_for(lang, "💎 Формати Little Legend", "💎 Форматы Little Legend",
                       "💎 Little Legend editions")
    digital_label = text_for(lang, "Цифрова книга PDF", "Цифровая книга PDF",
                             "Digital PDF book")
    print_label = text_for(lang, "Друкована книга", "Печатная книга",
                           "Printed book")
    note = text_for(
        lang,
        "Ціни довідкові. Оплата ще недоступна. Друкована версія готується.",
        "Цены справочные. Оплата пока недоступна. Печатная версия готовится.",
        "Prices are informational. Checkout is not yet available. Print is coming later.",
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=text_for(lang, "⬅️ Назад", "⬅️ Назад", "⬅️ Back"),
            callback_data="prod_little_legend",
        ),
    ]])
    await callback.message.answer(
        f"{heading}\n\n📱 {digital_label}: {digital_price}"
        f"\n📚 {print_label}: {physical_price} (⏳)"
        f"\n\n{note}",
        reply_markup=keyboard,
    )
    await callback.answer()
