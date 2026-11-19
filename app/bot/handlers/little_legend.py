"""Entry point for Little Legend as Food_Porn's third product."""
import logging
from urllib.parse import urlsplit, urlunsplit

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import select

from app.bot.handlers.wallpaper import language_for, text_for
from app.config import get_settings
from app.database.session import async_session_maker
from app.little_legend.aiogram_pdf_sender import AiogramPDFSender
from app.little_legend.art_storage_config import configured_generated_art_store
from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.owned_production import load_owned_production
from app.little_legend.pdf_storage_config import configured_private_pdf_store
from app.little_legend.readiness_messages import readiness_message
from app.little_legend.release_manifest_store import get_release_manifest
from app.little_legend.release_orchestrator import prepare_owned_release, send_owned_release
from app.little_legend.router import stories

logger = logging.getLogger(__name__)

router = Router(name="little_legend")


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
    buttons = []
    if studio_url:
        buttons.append([InlineKeyboardButton(
            text=text_for(lang, "📖 Відкрити студію", "📖 Открыть студию", "📖 Open story studio"),
            web_app=WebAppInfo(url=studio_url),
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
