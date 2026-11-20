"""Explicit parent review of completed Little Legend chapters in Telegram."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from fastapi import HTTPException
from sqlalchemy import select

from app.database.session import async_session_maker
from app.little_legend.manuscript_repository import (
    approve_chapter,
    mutate_owned_manuscript,
)
from app.little_legend.router import StoryDraft, stories
from app.little_legend.story_writer import StoryManuscript, manuscript_review

router = Router(name="little_legend_manuscript")


def review_text(draft: StoryDraft) -> str:
    """Do not claim final approval for missing or unexpected chapters."""
    if draft.graph is None:
        return "Сначала нужен план книги."
    manuscript = draft.manuscript or StoryManuscript(hero_name=draft.hero)
    report = manuscript_review(manuscript, draft.graph)
    chapters = {chapter.scene_id: chapter for chapter in manuscript.chapters}
    lines = ["📖 Проверка рукописи"]
    for node in sorted(draft.graph.nodes, key=lambda item: item.order):
        chapter = chapters.get(node.id)
        status = "⏳ Не написана" if chapter is None else (
            "✅ Утверждена" if chapter.approved else "📝 Требует проверки"
        )
        lines.append(f"{node.order}. {node.title}: {status}")
    if report["unexpected_scenes"]:
        lines.append("⚠️ Обнаружены главы вне утверждённого плана.")
    lines.append(
        "Итоговое утверждение: "
        + ("да" if manuscript.parent_approved else "нет")
    )
    return "\n".join(lines)


def _markup(story_id: int, draft: StoryDraft) -> InlineKeyboardMarkup:
    rows = []
    if draft.graph is not None and draft.manuscript is not None:
        chapters = {item.scene_id: item for item in draft.manuscript.chapters}
        for index, node in enumerate(
            sorted(draft.graph.nodes, key=lambda item: item.order),
        ):
            chapter = chapters.get(node.id)
            if chapter is not None and not chapter.approved:
                rows.append([InlineKeyboardButton(
                    text=f"📖 Читать главу {node.order}",
                    callback_data=f"ll_chapter:{story_id}:{index}",
                )])
        report = manuscript_review(draft.manuscript, draft.graph)
        if (
            not report["missing_scenes"]
            and not report["unexpected_scenes"]
            and not report["unapproved_scenes"]
            and not draft.manuscript.parent_approved
        ):
            rows.append([InlineKeyboardButton(
                text="✅ Утвердить всю рукопись",
                callback_data=f"ll_manuscript_final:{story_id}",
            )])
    rows.append([InlineKeyboardButton(
        text="⬅️ К книге", callback_data=f"ll_book:{story_id}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _owned(story_id: int, owner_id: int) -> StoryDraft | None:
    async with async_session_maker() as session:
        raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id,
            stories.c.owner_id == owner_id,
        ))).scalar_one_or_none()
    return StoryDraft.model_validate_json(raw) if raw is not None else None


def _parse(callback: CallbackQuery, count: int) -> list[int] | None:
    try:
        values = [int(value) for value in (callback.data or "").split(":")[1:]]
        if len(values) != count or any(value < 0 for value in values):
            return None
        if values[0] <= 0:
            return None
        return values
    except ValueError:
        return None


@router.callback_query(F.data.startswith("ll_manuscript_review:"))
async def show_review(callback: CallbackQuery) -> None:
    ids = _parse(callback, 1)
    if ids is None or callback.message is None:
        await callback.answer("Неверная книга", show_alert=True)
        return
    if callback.message.chat.type != "private":
        await callback.answer("Только в личном чате", show_alert=True)
        return
    draft = await _owned(ids[0], callback.from_user.id)
    if draft is None:
        await callback.answer("Книга не найдена", show_alert=True)
        return
    await callback.message.answer(
        review_text(draft), reply_markup=_markup(ids[0], draft),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_chapter:"))
async def show_chapter(callback: CallbackQuery) -> None:
    ids = _parse(callback, 2)
    if ids is None or callback.message is None:
        await callback.answer("Неверная глава", show_alert=True)
        return
    story_id, index = ids
    if callback.message.chat.type != "private":
        await callback.answer("Только в личном чате", show_alert=True)
        return
    draft = await _owned(story_id, callback.from_user.id)
    if draft is None or draft.graph is None or draft.manuscript is None:
        await callback.answer("Рукопись не найдена", show_alert=True)
        return
    nodes = sorted(draft.graph.nodes, key=lambda item: item.order)
    if index >= len(nodes):
        await callback.answer("Неверная глава", show_alert=True)
        return
    chapter = next(
        (item for item in draft.manuscript.chapters
         if item.scene_id == nodes[index].id), None,
    )
    if chapter is None:
        await callback.answer("Глава ещё не написана", show_alert=True)
        return
    # Telegram messages are limited to 4096 characters.
    await callback.message.answer(
        f"📖 Глава {nodes[index].order}: {nodes[index].title}",
    )
    for start in range(0, len(chapter.text), 3500):
        await callback.message.answer(chapter.text[start:start + 3500])
    rows = []
    if not chapter.approved:
        rows.append([InlineKeyboardButton(
            text="✅ Утвердить эту главу",
            callback_data=f"ll_chapter_approve:{story_id}:{index}",
        )])
    rows.append([InlineKeyboardButton(
        text="⬅️ К рукописи",
        callback_data=f"ll_manuscript_review:{story_id}",
    )])
    await callback.message.answer(
        "Проверьте текст перед утверждением.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_chapter_approve:"))
async def approve_one_chapter(callback: CallbackQuery) -> None:
    ids = _parse(callback, 2)
    if ids is None or callback.message is None:
        await callback.answer("Неверная глава", show_alert=True)
        return
    if callback.message.chat.type != "private":
        await callback.answer("Только в личном чате", show_alert=True)
        return
    story_id, index = ids

    def transform(manuscript: StoryManuscript, draft: StoryDraft) -> StoryManuscript:
        if draft.graph is None:
            raise ValueError("Missing outline")
        nodes = sorted(draft.graph.nodes, key=lambda item: item.order)
        if index >= len(nodes):
            raise ValueError("Unknown chapter")
        return approve_chapter(manuscript, nodes[index].id, True)

    try:
        await mutate_owned_manuscript(
            story_id=story_id, owner_id=callback.from_user.id,
            transform=transform,
        )
    except HTTPException:
        await callback.answer("Утверждение недоступно", show_alert=True)
        return
    await callback.message.answer(
        "✅ Глава утверждена. Вернитесь к проверке всей рукописи.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="📖 Проверить рукопись",
                callback_data=f"ll_manuscript_review:{story_id}",
            ),
        ]]),
    )
    await callback.answer()


def approve_complete_manuscript(
    manuscript: StoryManuscript, draft: StoryDraft,
) -> StoryManuscript:
    if draft.graph is None or not draft.graph.nodes:
        raise ValueError("Story outline is missing")
    if manuscript.hero_name != draft.hero:
        raise ValueError("Manuscript hero mismatch")
    report = manuscript_review(manuscript, draft.graph)
    if any(report[key] for key in (
        "missing_scenes", "unexpected_scenes", "unapproved_scenes",
    )):
        raise PermissionError("Every planned chapter must be approved")
    if not manuscript.chapters:
        raise PermissionError("No chapters written")
    return manuscript.model_copy(update={"parent_approved": True})


@router.callback_query(F.data.startswith("ll_manuscript_final:"))
async def approve_final(callback: CallbackQuery) -> None:
    ids = _parse(callback, 1)
    if ids is None or callback.message is None:
        await callback.answer("Неверная книга", show_alert=True)
        return
    if callback.message.chat.type != "private":
        await callback.answer("Только в личном чате", show_alert=True)
        return
    try:
        await mutate_owned_manuscript(
            story_id=ids[0], owner_id=callback.from_user.id,
            transform=approve_complete_manuscript,
        )
    except HTTPException:
        await callback.answer(
            "Сначала проверьте и утвердите все главы", show_alert=True,
        )
        return
    await callback.message.answer(
        "✅ Рукопись утверждена. Иллюстрации и выпуск PDF "
        "проверяются отдельно.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="📊 Производство книги",
                callback_data=f"ll_checkpoint:{ids[0]}",
            ),
        ]]),
    )
    await callback.answer()
