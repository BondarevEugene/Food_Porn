"""Entry point for Little Legend as Food_Porn's third product."""
import logging
import os
from urllib.parse import urlsplit, urlunsplit

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import select

from app.bot.handlers.little_legend_checkpoint import router as checkpoint_router
from app.bot.handlers.little_legend_context_help import router as context_help_router
from app.bot.handlers.little_legend_guided import router as guided_router
from app.bot.handlers.little_legend_illustrations import router as illustrations_router
from app.bot.handlers.little_legend_manuscript import router as manuscript_router
from app.bot.handlers.little_legend_outline import router as outline_router
from app.bot.handlers.little_legend_palettes import router as palette_router
from app.bot.handlers.little_legend_photo import router as photo_router
from app.bot.handlers.little_legend_release_preflight import router as release_preflight_router
from app.bot.handlers.wallpaper import language_for, text_for
from app.config import get_settings
from app.database.models import Customer
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
from app.little_legend.router import StoryDraft, stories

logger = logging.getLogger(__name__)

router = Router(name="little_legend")
router.include_router(context_help_router)
router.include_router(palette_router)
router.include_router(photo_router)
router.include_router(checkpoint_router)
router.include_router(manuscript_router)
router.include_router(illustrations_router)
router.include_router(release_preflight_router)
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



async def little_legend_language(user: object) -> str:
    """Use the persisted customer selection, not Telegram device language."""
    user_id = getattr(user, "id", None)
    if user_id is not None:
        async with async_session_maker() as session:
            saved = (await session.execute(
                select(Customer.language).where(Customer.telegram_user_id == user_id)
            )).scalar_one_or_none()
        if saved is not None:
            value = getattr(saved, "value", saved)
            if value in {"uk", "ru", "en"}:
                return value
    return language_for(user)


def _legend_home(lang: str, studio_url: str | None, *, expanded: bool):
    """Compact main actions; explanation expands in the same Telegram message."""
    buttons = [[InlineKeyboardButton(
        text=text_for(lang, "▶ Створити книгу", "▶ Создать книгу", "▶ Create book"),
        callback_data="ll_choose_mode",
    )]]
    if studio_url:
        buttons.append([InlineKeyboardButton(
            text=text_for(lang, "✏️ Редактор", "✏️ Редактор", "✏️ Editor"),
            web_app=WebAppInfo(url=studio_url),
        )])
    buttons.append([InlineKeyboardButton(
        text=text_for(lang, "📚 Мої книги", "📚 Мои книги", "📚 My books"),
        callback_data="ll_books",
    )])
    buttons.append([InlineKeyboardButton(
        text=text_for(lang, "ⓘ Згорнути підказку", "ⓘ Скрыть подсказку", "ⓘ Hide help")
        if expanded else text_for(lang, "ⓘ Що тут робити?", "ⓘ Что здесь делать?", "ⓘ What to do?"),
        callback_data="ll_home:hide" if expanded else "ll_home:help",
    )])
    buttons.append([InlineKeyboardButton(
        text=text_for(lang, "↩ До продуктів", "↩ К продуктам", "↩ Products"),
        callback_data="back_to_products",
    )])
    message = text_for(
        lang,
        "📖 <b>Little Legend</b>\nВаша дитина — герой книги.\n\n"
        "▶ <b>Створити книгу</b>\nОберіть сюжет і спосіб створення.\n"
        "✏️ <b>Редактор</b>\nЗмінюйте героїв, сцени й оформлення.\n"
        "📚 <b>Мої книги</b>\nПереглядайте та отримуйте готове.",
        "📖 <b>Little Legend</b>\nВаш ребёнок — герой книги.\n\n"
        "▶ <b>Создать книгу</b>\nВыберите сюжет и способ создания.\n"
        "✏️ <b>Редактор</b>\nМеняйте героев, сцены и оформление.\n"
        "📚 <b>Мои книги</b>\nПросматривайте и получайте готовое.",
        "📖 <b>Little Legend</b>\nYour child stars in a book.\n\n"
        "▶ <b>Create book</b>\nChoose a story and creation path.\n"
        "✏️ <b>Editor</b>\nEdit characters, scenes and design.\n"
        "📚 <b>My books</b>\nReview drafts and receive PDFs.",
    )
    if expanded:
        message += "\n\n" + text_for(
            lang,
            "ⓘ <b>Підказка</b>\n1. Почніть зі створення історії.\n"
            "2. У редакторі затвердьте сцени й ілюстрації.\n"
            "3. У «Мої книги» перевірте готовність PDF.\n"
            "Формати й ціни відкриваються з довідки. Оплата ще недоступна.",
            "ⓘ <b>Подсказка</b>\n1. Начните с создания истории.\n"
            "2. В редакторе утвердите сцены и иллюстрации.\n"
            "3. В «Мои книги» проверьте готовность PDF.\n"
            "Форматы и цены доступны через справку. Оплата пока недоступна.",
            "ⓘ <b>Help</b>\n1. Start by creating a story.\n"
            "2. Approve scenes and art in the editor.\n"
            "3. Check PDF readiness in My books.\n"
            "Editions and prices are in Help. Checkout is not available.",
        )
        buttons.insert(-2, [InlineKeyboardButton(
            text=text_for(lang, "💎 Формати й ціни", "💎 Форматы и цены", "💎 Editions & prices"),
            callback_data="ll_catalog",
        )])
    return message, InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "prod_little_legend")
async def open_little_legend(callback: CallbackQuery) -> None:
    lang = await little_legend_language(callback.from_user)
    studio_url = little_legend_studio_url(get_settings().miniapp_url)
    message, keyboard = _legend_home(lang, studio_url, expanded=False)
    await callback.message.answer(message, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.in_({"ll_home:help", "ll_home:hide"}))
async def toggle_little_legend_home_help(callback: CallbackQuery) -> None:
    """Expand/collapse inline without replacing the user's current selection."""
    lang = await little_legend_language(callback.from_user)
    studio_url = little_legend_studio_url(get_settings().miniapp_url)
    expanded = callback.data == "ll_home:help"
    message, keyboard = _legend_home(lang, studio_url, expanded=expanded)
    await callback.message.edit_text(message, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "ll_help")
async def show_little_legend_help(callback: CallbackQuery) -> None:
    lang = await little_legend_language(callback.from_user)
    message = text_for(
        lang,
        "❓ <b>Як працює Little Legend</b>\n\n"
        "✨ <b>Створити книгу</b> — оберіть спосіб створення історії. "
        "Режим «Моя історія» відкриває покрокову роботу над сюжетом.\n\n"
        "🎨 <b>Редактор книги</b> — студія для роботи над героями, сценами, "
        "ілюстраціями та перевіркою результату. Це не окремий платний формат.\n\n"
        "💎 <b>Формати й ціни</b> — цифровий PDF або майбутня друкована версія.\n\n"
        "📚 <b>Мої книги</b> — чернетки, перевірки, підготовка й отримання PDF.\n\n"
        "<b>Порядок:</b> створіть історію → відредагуйте й затвердьте "
        "сцени → перевірте ілюстрації → підготуйте PDF → отримайте книгу. "
        "Оплата ще недоступна.",
        "❓ <b>Как работает Little Legend</b>\n\n"
        "✨ <b>Создать книгу</b> — выбрать способ создания истории. "
        "Режим «Моя история» ведёт к пошаговой работе над сюжетом.\n\n"
        "🎨 <b>Редактор книги</b> — студия для работы с героями, сценами, "
        "иллюстрациями и проверки результата. Это не отдельный платный формат.\n\n"
        "💎 <b>Форматы и цены</b> — цифровой PDF или будущая печатная версия.\n\n"
        "📚 <b>Мои книги</b> — черновики, проверки, подготовка и получение PDF.\n\n"
        "<b>Порядок:</b> создайте историю → отредактируйте и утвердите "
        "сцены → проверьте иллюстрации → подготовьте PDF → получите книгу. "
        "Оплата пока недоступна.",
        "❓ <b>How Little Legend works</b>\n\n"
        "✨ <b>Create a book</b> — choose a story creation path. "
        "My Story leads to the guided story workflow.\n\n"
        "🎨 <b>Book editor</b> — a studio for characters, scenes, illustrations "
        "and reviewing the result. It is not a separate paid edition.\n\n"
        "💎 <b>Editions & prices</b> — digital PDF or a future print edition.\n\n"
        "📚 <b>My books</b> — drafts, reviews, preparation and PDF delivery.\n\n"
        "<b>Order:</b> create a story → review and approve scenes → "
        "review illustrations → prepare PDF → receive the book. "
        "Checkout is not yet available.",
    )
    await callback.message.answer(
        message,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=text_for(lang, "⬅️ До книги", "⬅️ К книге", "⬅️ Back to book"),
                callback_data="prod_little_legend",
            ),
        ]]),
    )
    await callback.answer()


@router.callback_query(F.data == "ll_choose_mode")
async def choose_little_legend_mode(callback: CallbackQuery) -> None:
    """One clear decision per screen; preserve the existing editor route."""
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Open this in a private chat", show_alert=True)
        return
    lang = await little_legend_language(callback.from_user)
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
        text_for(
            lang,
            "📖 <b>Крок 1/5 · Оберіть спосіб</b>\n\n"
            "✍️ <b>Моя історія</b> — ви керуєте сюжетом.\n"
            "🏰 <b>Герой казки</b> — адаптація готується.\n"
            "✨ <b>За моєю ідеєю</b> — редактор готується.\n\n"
            "ⓘ Почніть із «Моя історія».",
            "📖 <b>Шаг 1/5 · Выберите способ</b>\n\n"
            "✍️ <b>Моя история</b> — управляйте сюжетом сами.\n"
            "🏰 <b>Герой сказки</b> — адаптация готовится.\n"
            "✨ <b>По моей идее</b> — редактор готовится.\n\n"
            "ⓘ Начните с «Моя история».",
            "📖 <b>Step 1/5 · Choose a path</b>\n\n"
            "✍️ <b>My story</b> — direct the plot yourself.\n"
            "🏰 <b>Classic hero</b> — coming later.\n"
            "✨ <b>My idea</b> — editor coming later.\n\n"
            "ⓘ Start with My story.",
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data == "ll_mode:director")
async def show_little_legend_mode(callback: CallbackQuery) -> None:
    """Explain mode readiness without pretending an unsupported editor is live."""
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Open this in a private chat", show_alert=True)
        return
    lang = await little_legend_language(callback.from_user)
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
    lang = await little_legend_language(callback.from_user)
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
        owned = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ))).scalar_one_or_none()
    if owned is None:
        await callback.answer("Book not found", show_alert=True)
        return
    lang = await little_legend_language(callback.from_user)
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
    draft = StoryDraft.model_validate_json(owned)
    plan_done = draft.graph is not None and draft.parent_sketch is not None
    approved = plan_done and draft.outline_approved and draft.entry.plan_approved
    hero_done = (
        draft.blueprint is not None and draft.blueprint.family_approved
    )
    manuscript_done = (
        draft.manuscript is not None and draft.manuscript.parent_approved
    )
    steps = [
        ("Идея и герой", bool(draft.hero.strip()), f"ll_book:{story_id}"),
        ("План истории", plan_done, f"ll_outline:{story_id}"),
        ("Утверждение плана", approved, f"ll_outline:{story_id}"),
        ("Профиль героя", hero_done, f"ll_book:{story_id}"),
        ("Рукопись", manuscript_done, f"ll_manuscript_review:{story_id}"),
        ("Иллюстрации", bool(ready_for_assembly or status), f"ll_art_ready:{story_id}"),
        ("Готовый PDF", bool(status), f"ll_release_review:{story_id}"),
        ("Доставка", status == DeliveryStatus.SENT, f"ll_send:{story_id}"),
    ]
    complete = sum(bool(done) for _, done, _ in steps)
    first = next(
        ((label, action) for label, done, action in steps if not done),
        None,
    )
    checklist = "\n".join(
        f"{'✅' if done else '❌'} {label}" for label, done, _ in steps
    )
    if first is not None and first[1] == f"ll_book:{story_id}":
        # A book overview is not a completion action: direct the user to
        # the existing guided editor instead of creating a self-loop.
        first = (first[0], f"ll_outline:{story_id}")
    buttons = []
    if callback.message.chat.type == "private":
        if status == DeliveryStatus.READY:
            primary = ("📥 Получить готовый PDF", f"ll_send:{story_id}")
        elif ready_for_assembly:
            primary = ("📘 Подготовить книгу", f"ll_prepare:{story_id}")
        elif first is not None:
            primary = (f"▶ Продолжить: {first[0]}", first[1])
        else:
            primary = ("📊 Проверить производство", f"ll_checkpoint:{story_id}")
        buttons.append([InlineKeyboardButton(
            text=primary[0], callback_data=primary[1],
        )])
        buttons.append([InlineKeyboardButton(
            text="⚙️ Дополнительные действия",
            callback_data=f"ll_book_tools:{story_id}",
        )])
    buttons.append([InlineKeyboardButton(
        text="⬅️ Мои книги", callback_data="ll_books",
    )])
    await callback.message.answer(
        f"📖 Книга №{story_id} · {status_text}\n"
        f"Выполнено {complete} из {len(steps)} обязательных этапов\n\n"
        f"{checklist}\n\n"
        + (f"{readiness_text}\n\n" if readiness_text else "")
        + "Нажмите основную кнопку, чтобы продолжить.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_book_tools:"))
async def little_legend_book_tools(callback: CallbackQuery) -> None:
    """Keep optional and destructive actions away from the primary route."""
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Только в личном чате", show_alert=True)
        return
    try:
        story_id = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Неверная книга", show_alert=True)
        return
    async with async_session_maker() as session:
        owned = (await session.execute(select(stories.c.id).where(
            stories.c.id == story_id,
            stories.c.owner_id == callback.from_user.id,
        ))).scalar_one_or_none()
    if owned is None:
        await callback.answer("Книга не найдена", show_alert=True)
        return
    actions = [
        ("📖 Рукопись", f"ll_manuscript_review:{story_id}"),
        ("🎨 Иллюстрации", f"ll_art_ready:{story_id}"),
        ("🎨 Оформление", f"ll_palette:{story_id}"),
        ("📷 Фото и согласие", f"ll_photo_notice:{story_id}"),
        ("📊 Производство", f"ll_checkpoint:{story_id}"),
        ("📘 Выпуск PDF", f"ll_release_review:{story_id}"),
        ("🗑 Удалить фото и отозвать согласие", f"ll_photo_withdraw:{story_id}"),
        ("⬅️ К этапам книги", f"ll_book:{story_id}"),
    ]
    outline_button = InlineKeyboardButton(\n        text="📖 Посмотреть и утвердить план",\n        callback_data=f"ll_outline:{story_id}",\n    )\n    await callback.message.answer(\n        "⚙️ Дополнительные действия\\n"
        "Они не заменяют обязательные этапы создания книги.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=data)]
            for label, data in actions
        ] + [[outline_button]]),
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
            registry_bucket=os.environ.get("LITTLE_LEGEND_S3_BUCKET") or None,
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
    lang = await little_legend_language(callback.from_user)
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
        "Цифровий формат — ілюстрований PDF для читання та збереження. "
        "Друкований формат передбачає фізичну книгу й доставку, але ще не запущений. "
        "Ціни встановлюються адміністратором у Mini CRM; відсутня ціна означає, "
        "що тариф не налаштований. Оплата ще недоступна.",
        "Цифровой формат — иллюстрированный PDF для чтения и сохранения. "
        "Печатный формат предполагает физическую книгу и доставку, но ещё не запущен. "
        "Цены задаёт администратор в Mini CRM; прочерк означает, что тариф не настроен. "
        "Оплата пока недоступна.",
        "Digital edition is an illustrated PDF. Print edition would include a physical "
        "book and shipping, but is not launched yet. The administrator sets prices "
        "in Mini CRM; a dash means no price is configured. Checkout is not available.",
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
