"""Entry point for Little Legend as Food_Porn's third product."""
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.bot.handlers.wallpaper import language_for, text_for
from app.config import get_settings

router = Router(name="little_legend")


@router.callback_query(F.data == "prod_little_legend")
async def open_little_legend(callback: CallbackQuery) -> None:
    lang = language_for(callback.from_user)
    base_url = get_settings().miniapp_url.strip().rstrip("/")
    buttons = []
    if base_url.startswith("https://"):
        buttons.append([InlineKeyboardButton(
            text=text_for(lang, "📖 Відкрити студію", "📖 Открыть студию", "📖 Open story studio"),
            web_app=WebAppInfo(url=base_url + "/little-legend"),
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
    if not base_url.startswith("https://"):
        message += "\n\n" + text_for(
            lang, "Студія стане доступною після налаштування MINIAPP_URL (HTTPS).",
            "Студия станет доступна после настройки MINIAPP_URL (HTTPS).",
            "The studio will open once MINIAPP_URL (HTTPS) is configured.",
        )
    await callback.message.answer(message, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()
