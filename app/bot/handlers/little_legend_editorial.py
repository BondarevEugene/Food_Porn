"""Explicit owner-scoped parental editorial review before PDF assembly."""
from __future__ import annotations

from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, update

from app.database.session import async_session_maker
from app.little_legend.editorial_review import EditorialDecision
from app.little_legend.router import StoryDraft, stories
from app.little_legend.story_writer import manuscript_review

router = Router(name="little_legend_editorial")


def _story_id(callback: CallbackQuery) -> int | None:
    try:
        value = int((callback.data or "").split(":", 1)[1])
        return value if value > 0 else None
    except (IndexError, ValueError):
        return None


def _allowed(callback: CallbackQuery) -> bool:
    return bool(
        callback.message
        and callback.message.chat.type == "private"
        and callback.message.chat.id == callback.from_user.id
    )


def editorial_ready(draft: StoryDraft) -> bool:
    """No parental editorial sign-off before a complete approved manuscript."""
    if draft.graph is None or draft.manuscript is None:
        return False
    if draft.blueprint is None or not draft.blueprint.family_approved:
        return False
    if draft.manuscript.hero_name != draft.hero:
        return False
    if not draft.graph.nodes:
        return False
    return bool(manuscript_review(draft.manuscript, draft.graph)["structurally_approved"])


def _navigation(story_id: int, *, confirm: bool) -> InlineKeyboardMarkup:
    rows = []
    if confirm:
        rows.append([InlineKeyboardButton(
            text="✅ Подтверждаю проверку всей книги",
            callback_data=f"ll_editorial_accept:{story_id}",
        )])
    rows.append([InlineKeyboardButton(
        text="📖 Проверить главы",
        callback_data=f"ll_manuscript_review:{story_id}",
    )])
    rows.append([InlineKeyboardButton(
        text="⬅️ К этапам книги", callback_data=f"ll_book:{story_id}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("ll_editorial:"))
async def show_editorial(callback: CallbackQuery) -> None:
    story_id = _story_id(callback)
    if story_id is None or not _allowed(callback):
        await callback.answer("Доступно только владельцу книги", show_alert=True)
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
    already = all((
        draft.editorial_decision.hero_fidelity_reviewed,
        draft.editorial_decision.age_appropriateness_reviewed,
        draft.editorial_decision.narrative_continuity_reviewed,
        draft.editorial_decision.parent_final_approval,
    ))
    ready = editorial_ready(draft)
    if already:
        message = "✅ Финальная проверка уже подтверждена и сохранена."
    elif not ready:
        message = (
            "❌ Сначала прочитайте и утвердите все главы рукописи. "
            "Пока не все обязательные условия выполнены."
        )
    else:
        message = (
            f"📖 Финальная проверка: «{draft.title}»\n"
            f"Герой: {draft.hero}\n"
            f"Глав в книге: {len(draft.graph.nodes)}\n\n"
            "Перед подтверждением прочитайте главы и убедитесь, что:\n"
            "• герой узнаваем и его описание соответствует вашему замыслу;\n"
            "• содержание подходит ребёнку по возрасту;\n"
            "• история последовательна и не содержит нежелательных деталей;\n"
            "• вы окончательно одобряете рукопись.\n\n"
            "Это подтверждение не запускает AI, оплату или сборку PDF. "
            "Иллюстрации проверяются отдельно."
        )
    await callback.message.answer(
        message,
        reply_markup=_navigation(story_id, confirm=ready and not already),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_editorial_accept:"))
async def accept_editorial(callback: CallbackQuery) -> None:
    story_id = _story_id(callback)
    if story_id is None or not _allowed(callback):
        await callback.answer("Доступно только владельцу книги", show_alert=True)
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
        if not editorial_ready(draft):
            await callback.answer(
                "Сначала утвердите рукопись и профиль героя", show_alert=True,
            )
            return
        draft.editorial_decision = EditorialDecision(
            hero_fidelity_reviewed=True,
            age_appropriateness_reviewed=True,
            narrative_continuity_reviewed=True,
            parent_final_approval=True,
        )
        await session.execute(update(stories).where(
            stories.c.id == story_id,
            stories.c.owner_id == callback.from_user.id,
        ).values(data=draft.model_dump_json(), updated_at=datetime.now(UTC)))
        await session.commit()
    await callback.message.answer(
        "✅ Финальная проверка сохранена. "
        "Теперь вернитесь к этапам книги: сборка PDF будет доступна "
        "только после завершения иллюстраций.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="▶ Продолжить создание книги",
                callback_data=f"ll_book:{story_id}",
            ),
        ]]),
    )
    await callback.answer()
