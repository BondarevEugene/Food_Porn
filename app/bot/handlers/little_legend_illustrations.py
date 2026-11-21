"""Explicit, owner-scoped illustration launch after parental manuscript approval."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.bot.handlers.little_legend_context_help import (
    help_button,
    selected_language,
    stage_message,
)
from app.database.session import async_session_maker
from app.little_legend.illustration_queue_store import enqueue_illustration_jobs
from app.little_legend.router import StoryDraft, stories

router = Router(name="little_legend_illustration_launch")


def approved_scene_ids(draft: StoryDraft) -> list[str]:
    """Return the exact planned scene set only for a fully approved manuscript."""
    if draft.graph is None or not draft.graph.nodes or draft.manuscript is None:
        return []
    manuscript = draft.manuscript
    expected = [node.id for node in sorted(draft.graph.nodes, key=lambda n: n.order)]
    chapters = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    if (
        len(set(expected)) != len(expected)
        or len(chapters) != len(manuscript.chapters)
        or set(chapters) != set(expected)
        or not manuscript.parent_approved
        or manuscript.hero_name != draft.hero
        or any(not chapter.approved for chapter in chapters.values())
    ):
        return []
    return expected


def _parse_id(callback: CallbackQuery) -> int | None:
    try:
        story_id = int((callback.data or "").split(":", 1)[1])
        return story_id if story_id > 0 else None
    except (ValueError, IndexError):
        return None


async def _load_owned(story_id: int, owner_id: int) -> StoryDraft | None:
    async with async_session_maker() as session:
        raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id,
            stories.c.owner_id == owner_id,
        ))).scalar_one_or_none()
    return StoryDraft.model_validate_json(raw) if raw is not None else None


def _navigation(story_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📊 Производство книги",
            callback_data=f"ll_checkpoint:{story_id}",
        ),
    ]])


@router.callback_query(F.data.startswith("ll_art_ready:"))
async def show_art_readiness(callback: CallbackQuery) -> None:
    story_id = _parse_id(callback)
    if story_id is None or callback.message is None:
        await callback.answer("Неверная книга", show_alert=True)
        return
    if callback.message.chat.type != "private":
        await callback.answer("Только в личном чате", show_alert=True)
        return
    draft = await _load_owned(story_id, callback.from_user.id)
    if draft is None:
        await callback.answer("Книга не найдена", show_alert=True)
        return
    scenes = approved_scene_ids(draft)
    rows = []
    if scenes:
        text = (
            f"🎨 Рукопись утверждена. Иллюстраций для подготовки: {len(scenes)}. "
            "Перед платной генерацией необходимо подтвердить запуск. "
            "Сервер повторно проверит согласие на AI-изображения, "
            "профиль героя и лимит расходов."
        )
        rows.append([InlineKeyboardButton(
            text="🎨 Подтвердить генерацию иллюстраций",
            callback_data=f"ll_art_confirm:{story_id}",
        )])
    else:
        text = (
            "⏳ Иллюстрации пока недоступны. Сначала нужно "
            "утвердить каждую главу и всю рукопись."
        )
    lang = await selected_language(callback.from_user)
    rows.append([help_button(lang, "art", story_id)])
    rows.extend(_navigation(story_id).inline_keyboard)
    await callback.message.answer(
        text + "\n\n" + stage_message(lang, "art"),
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_art_confirm:"))
async def confirm_art_launch(callback: CallbackQuery) -> None:
    story_id = _parse_id(callback)
    if story_id is None or callback.message is None:
        await callback.answer("Неверная книга", show_alert=True)
        return
    if callback.message.chat.type != "private":
        await callback.answer("Только в личном чате", show_alert=True)
        return
    draft = await _load_owned(story_id, callback.from_user.id)
    if draft is None:
        await callback.answer("Книга не найдена", show_alert=True)
        return
    scenes = approved_scene_ids(draft)
    if not scenes:
        await callback.answer("Сначала утвердите рукопись", show_alert=True)
        return
    try:
        job_ids = await enqueue_illustration_jobs(
            story_id=story_id,
            owner_id=callback.from_user.id,
            scene_ids=scenes,
        )
    except (PermissionError, ValueError):
        await callback.answer(
            "Запуск недоступен: проверьте согласия, профиль и статус заказа",
            show_alert=True,
        )
        return
    await callback.message.answer(
        f"🎨 Иллюстрации поставлены в очередь: {len(job_ids)}. "
        "Повторная постановка защищена на уровне базы данных.",
        reply_markup=_navigation(story_id),
    )
    await callback.answer()
