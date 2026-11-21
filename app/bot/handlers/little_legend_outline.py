"""Owner-scoped Telegram review of Little Legend parental story plans."""
from __future__ import annotations

from datetime import UTC, datetime
from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, update

from app.bot.handlers.little_legend_context_help import (
    help_button,
    selected_language,
    stage_message,
)
from app.database.session import async_session_maker
from app.little_legend.router import StoryDraft, stories
from app.little_legend.story_modes import StoryMode
from app.little_legend.telegram_writer_readiness import chapter_readiness

router = Router(name="little_legend_outline")


def _keyboard(story_id: int, *, approvable: bool) -> InlineKeyboardMarkup:
    rows = []
    if approvable:
        rows.append([InlineKeyboardButton(
            text="✅ Утвердить план",
            callback_data=f"ll_outline_approve:{story_id}",
        )])
    rows.append([InlineKeyboardButton(
        text="🧩 Проверить готовность к написанию",
        callback_data=f"ll_writer_ready:{story_id}",
    )])
    rows.append([InlineKeyboardButton(
        text="⬅️ К книге", callback_data=f"ll_book:{story_id}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _story_id(callback: CallbackQuery) -> int | None:
    try:
        value = int((callback.data or "").split(":", 1)[1])
        return value if value > 0 else None
    except (IndexError, ValueError):
        return None


def _preview(draft: StoryDraft) -> str:
    if draft.graph is None:
        return "План пока не составлен."
    parts = [
        f"{node.order}. {(node.summary or node.goal or 'Сцена без описания')[:180]}"
        for node in draft.graph.nodes[:12]
    ]
    return "📖 План книги:\n\n" + "\n".join(parts)


@router.callback_query(F.data.startswith("ll_outline:"))
async def show_outline(callback: CallbackQuery) -> None:
    story_id = _story_id(callback)
    if story_id is None or callback.message is None:
        await callback.answer("Неверная книга", show_alert=True)
        return
    if callback.message.chat.type != "private":
        await callback.answer("Только в личном чате", show_alert=True)
        return
    async with async_session_maker() as session:
        raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id,
            stories.c.owner_id == callback.from_user.id,
        ))).scalar_one_or_none()
    if raw is None:
        await callback.answer("Книга не найдена", show_alert=True)
        return
    draft = StoryDraft.model_validate_json(raw)
    classic_blocked = (
        draft.entry.mode == StoryMode.CLASSIC
        and (
            draft.entry.classic is None
            or not draft.entry.classic.public_domain_verified
        )
    )
    approvable = (
        draft.graph is not None and draft.parent_sketch is not None
        and not draft.outline_approved and not classic_blocked
    )
    note = (
        "\n\n⚠️ Для классики требуется подтверждение прав на источник."
        if classic_blocked else ""
    )
    status = "\n\n✅ План уже утверждён." if draft.outline_approved else ""
    lang = await selected_language(callback.from_user)
    keyboard = _keyboard(story_id, approvable=approvable)
    keyboard.inline_keyboard.insert(-1, [help_button(lang, "outline", story_id)])
    await callback.message.answer(
        escape(_preview(draft) + note + status) + "\n\n" + stage_message(lang, "outline"),
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_outline_approve:"))
async def approve_outline(callback: CallbackQuery) -> None:
    story_id = _story_id(callback)
    if story_id is None or callback.message is None:
        await callback.answer("Неверная книга", show_alert=True)
        return
    if callback.message.chat.type != "private":
        await callback.answer("Только в личном чате", show_alert=True)
        return
    async with async_session_maker() as session:
        raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id,
            stories.c.owner_id == callback.from_user.id,
        ).with_for_update())).scalar_one_or_none()
        if raw is None:
            await callback.answer("Книга не найдена", show_alert=True)
            return
        draft = StoryDraft.model_validate_json(raw)
        if draft.graph is None or draft.parent_sketch is None:
            await callback.answer("Сначала создайте план", show_alert=True)
            return
        if draft.entry.mode == StoryMode.CLASSIC and (
            draft.entry.classic is None
            or not draft.entry.classic.public_domain_verified
        ):
            await callback.answer("Сначала подтвердите права на источник", show_alert=True)
            return
        if draft.manuscript is not None and draft.manuscript.chapters:
            await callback.answer("У книги уже есть рукопись", show_alert=True)
            return
        draft.outline_approved = True
        draft.entry.plan_approved = True
        await session.execute(update(stories).where(
            stories.c.id == story_id,
            stories.c.owner_id == callback.from_user.id,
        ).values(data=draft.model_dump_json(), updated_at=datetime.now(UTC)))
        await session.commit()
    await callback.message.answer(
        "✅ План утверждён. Это не запускает платную генерацию. "
        "Для написания глав ещё нужны профиль героя и согласие на AI.",
        reply_markup=_keyboard(story_id, approvable=False),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_writer_ready:"))
async def show_writer_readiness(callback: CallbackQuery) -> None:
    story_id = _story_id(callback)
    if story_id is None or callback.message is None:
        await callback.answer("Неверная книга", show_alert=True)
        return
    if callback.message.chat.type != "private":
        await callback.answer("Только в личном чате", show_alert=True)
        return
    async with async_session_maker() as session:
        raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id,
            stories.c.owner_id == callback.from_user.id,
        ))).scalar_one_or_none()
    if raw is None:
        await callback.answer("Книга не найдена", show_alert=True)
        return
    report = chapter_readiness(StoryDraft.model_validate_json(raw))
    if report["ready"]:
        text = (
            "✅ Основные условия написания глав выполнены. "
            "Платная генерация не запущена. "
            "Следующий шаг — отдельное подтверждение запуска."
        )
    else:
        text = "🧩 Что осталось до написания книги:\n\n" + "\n".join(
            f"• {reason}" for reason in report["blockers"]
        )
    await callback.message.answer(
        text, reply_markup=_keyboard(story_id, approvable=False),
    )
    await callback.answer()
