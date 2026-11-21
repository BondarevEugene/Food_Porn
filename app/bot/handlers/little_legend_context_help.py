"""Compact, reversible contextual guidance for Little Legend Telegram stages.

Help is displayed by editing the same message. No FSM changes, no new
messages and no mutations of a book or paid-production state.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.bot.handlers.wallpaper import language_for, text_for
from app.database.models import Customer
from app.database.session import async_session_maker

router = Router(name="little_legend_context_help")

STAGES = {
    "outline": (
        ("📖 План книги", "📖 План книги", "📖 Book outline"),
        ("Перевірте порядок сцен. Затверджуйте лише правильний план.",
         "Проверьте порядок сцен. Утверждайте только верный план.",
         "Review scene order. Approve only a correct outline."),
        ("План задає послідовність історії. Після затвердження "
         "можна переходити до написання глав. Затвердження "
         "не запускає платну генерацію.",
         "План задаёт последовательность истории. После утверждения "
         "можно переходить к написанию глав. Утверждение "
         "не запускает платную генерацию.",
         "The outline sets story order. After approval, chapters can "
         "be written. Approval does not trigger paid generation."),
    ),
    "art": (
        ("🎨 Ілюстрації", "🎨 Иллюстрации", "🎨 Illustrations"),
        ("Спершу затвердіть текст усіх глав.",
         "Сначала утвердите текст всех глав.",
         "Approve all chapter text first."),
        ("Ілюстрації створюються лише після затвердження рукопису. "
         "Перед запуском перевіряються згода, герой та ліміт витрат. "
         "Натискання підтвердження може поставити платні завдання в чергу.",
         "Иллюстрации создаются только после утверждения рукописи. "
         "Перед запуском проверяются согласие, герой и лимит расходов. "
         "Подтверждение может поставить платные задания в очередь.",
         "Illustrations require an approved manuscript. Consent, hero "
         "and budget are checked before launch. Confirmation can enqueue "
         "paid generation jobs."),
    ),
    "release": (
        ("📘 Випуск PDF", "📘 Выпуск PDF", "📘 PDF release"),
        ("Перевірте готовність і отримайте книгу.",
         "Проверьте готовность и получите книгу.",
         "Check readiness and receive the book."),
        ("PDF збирається з уже готових матеріалів. Якщо перевірки "
         "не пройдено, спершу виправте книгу. Після підготовки "
         "завантажте готовий PDF. Повторне надсилання обмежене.",
         "PDF собирается из уже готовых материалов. Если проверки "
         "не пройдены, сначала исправьте книгу. После подготовки "
         "получите готовый PDF. Повторная отправка ограничена.",
         "PDF assembly uses existing approved materials. Resolve any "
         "blocking checks first. Receive the PDF once ready. "
         "Repeated delivery is restricted."),
    ),
}


async def selected_language(user: object) -> str:
    user_id = getattr(user, "id", None)
    if user_id is not None:
        async with async_session_maker() as session:
            saved = (await session.execute(
                select(Customer.language).where(Customer.telegram_user_id == user_id)
            )).scalar_one_or_none()
        value = getattr(saved, "value", saved)
        if value in {"uk", "ru", "en"}:
            return value
    return language_for(user)


def stage_message(lang: str, stage: str, *, expanded: bool = False) -> str:
    title, summary, details = STAGES[stage]
    result = f"<b>{text_for(lang, *title)}</b>\n{text_for(lang, *summary)}"
    if expanded:
        result += "\n\nⓘ " + text_for(lang, *details)
    return result


def help_button(lang: str, stage: str, story_id: int, *, expanded: bool = False):
    return InlineKeyboardButton(
        text=text_for(lang, "ⓘ Згорнути", "ⓘ Скрыть", "ⓘ Hide")
        if expanded else text_for(lang, "ⓘ Підказка", "ⓘ Подсказка", "ⓘ Help"),
        callback_data=f"ll_context:{stage}:{story_id}:{'hide' if expanded else 'show'}",
    )


@router.callback_query(F.data.startswith("ll_context:"))
async def toggle_stage_help(callback: CallbackQuery) -> None:
    if (
        callback.message is None
        or callback.message.chat.type != "private"
        or callback.message.chat.id != callback.from_user.id
    ):
        await callback.answer("Private chat required", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4 or parts[1] not in STAGES or parts[3] not in {"show", "hide"}:
        await callback.answer("Invalid help request", show_alert=True)
        return
    try:
        story_id = int(parts[2])
        if story_id <= 0:
            raise ValueError
    except ValueError:
        await callback.answer("Invalid book", show_alert=True)
        return
    from app.little_legend.router import stories

    async with async_session_maker() as session:
        owned = (await session.execute(
            select(stories.c.id).where(
                stories.c.id == story_id,
                stories.c.owner_id == callback.from_user.id,
            )
        )).scalar_one_or_none()
    if owned is None:
        await callback.answer("Book not found", show_alert=True)
        return
    lang = await selected_language(callback.from_user)
    expanded = parts[3] == "show"
    # Preserve the original action buttons, changing only the help control.
    rows = []
    current = callback.message.reply_markup
    if current is not None:
        for row in current.inline_keyboard:
            rows.append([
                help_button(lang, parts[1], story_id, expanded=expanded)
                if (button.callback_data or "").startswith(
                    f"ll_context:{parts[1]}:{story_id}:"
                ) else button
                for button in row
            ])
    text = callback.message.html_text or callback.message.text or ""
    # The summary is a stable prefix; stage screens put it at the end.
    marker = stage_message(lang, parts[1])
    # Strip any previously expanded context by replacing the known suffix.
    for suffix in (stage_message(lang, parts[1], expanded=True), marker):
        if text.endswith(suffix):
            text = text[: -len(suffix)].rstrip()
            break
    text = (text + "\n\n" if text else "") + stage_message(
        lang, parts[1], expanded=expanded,
    )
    await callback.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()
