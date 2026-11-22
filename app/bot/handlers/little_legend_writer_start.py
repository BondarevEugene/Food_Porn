"""Telegram-native parental terms and explicit chapter queue start."""
from __future__ import annotations

from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from fastapi import HTTPException
from sqlalchemy import select, update

from app.database.session import async_session_maker
from app.little_legend.consent import (
    TERMS,
    ConsentDecision,
    consent_status,
    record_decision,
)
from app.little_legend.router import StoryDraft, stories
from app.little_legend.sketch_enqueue import enqueue_sketch_chapters
from app.little_legend.telegram_writer_readiness import chapter_readiness

router = Router(name="little_legend_writer_start")


def _id(callback: CallbackQuery) -> int | None:
    try:
        value = int((callback.data or "").split(":", 1)[1])
        return value if value > 0 else None
    except (IndexError, ValueError):
        return None


def _private(callback: CallbackQuery) -> bool:
    return bool(callback.message and callback.message.chat.type == "private")


def _button(label: str, action: str) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=label, callback_data=action)]


async def _owned(story_id: int, owner_id: int) -> StoryDraft | None:
    async with async_session_maker() as session:
        raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ))).scalar_one_or_none()
    return StoryDraft.model_validate_json(raw) if raw is not None else None


@router.callback_query(F.data.startswith("ll_terms:"))
async def show_terms(callback: CallbackQuery) -> None:
    story_id = _id(callback)
    if not _private(callback) or story_id is None:
        await callback.answer("Неверная книга", show_alert=True)
        return
    draft = await _owned(story_id, callback.from_user.id)
    if draft is None:
        await callback.answer("Книга не найдена", show_alert=True)
        return
    accepted = consent_status(draft.consent)["terms_accepted"]
    rows = [] if accepted else [
        _button("✅ Принимаю условия и подтверждаю полномочия родителя",
                f"ll_terms_accept:{story_id}"),
    ]
    rows.append(_button("⬅️ К книге", f"ll_book:{story_id}"))
    await callback.message.answer(
        ("✅ Условия уже приняты." if accepted else TERMS),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_terms_accept:"))
async def accept_terms(callback: CallbackQuery) -> None:
    story_id = _id(callback)
    if not _private(callback) or story_id is None:
        await callback.answer("Неверная книга", show_alert=True)
        return
    async with async_session_maker() as session:
        raw = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id, stories.c.owner_id == callback.from_user.id,
        ).with_for_update())).scalar_one_or_none()
        if raw is None:
            await callback.answer("Книга не найдена", show_alert=True)
            return
        draft = StoryDraft.model_validate_json(raw)
        if not consent_status(draft.consent)["terms_accepted"]:
            draft.consent = record_decision(
                draft.consent, ConsentDecision(
                    accept_terms=True, declare_parental_authority=True,
                ),
            )
            await session.execute(update(stories).where(
                stories.c.id == story_id,
                stories.c.owner_id == callback.from_user.id,
            ).values(data=draft.model_dump_json(), updated_at=datetime.now(UTC)))
            await session.commit()
    await callback.message.answer(
        "✅ Условия и полномочия родителя сохранены. "
        "Это не является согласием на обработку фотографий или текста AI.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            _button("▶ Продолжить", f"ll_book:{story_id}"),
        ]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_writer_start:"))
async def show_writer_start(callback: CallbackQuery) -> None:
    story_id = _id(callback)
    if not _private(callback) or story_id is None:
        await callback.answer("Неверная книга", show_alert=True)
        return
    draft = await _owned(story_id, callback.from_user.id)
    if draft is None:
        await callback.answer("Книга не найдена", show_alert=True)
        return
    if draft.manuscript is not None and draft.manuscript.parent_approved:
        await callback.message.answer(
            "✅ Рукопись уже утверждена.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                _button("▶ Продолжить", f"ll_book:{story_id}"),
            ]),
        )
        await callback.answer()
        return
    if draft.writer_job_ids:
        await callback.message.answer(
            "📖 Для этой книги уже создавались задания на написание. "
            "Проверьте готовые главы, прежде чем запускать повторно.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                _button("📖 Проверить главы", f"ll_manuscript_review:{story_id}"),
                _button("⬅️ К книге", f"ll_book:{story_id}"),
            ]),
        )
        await callback.answer()
        return
    readiness = chapter_readiness(draft)
    rows = []
    if readiness["ready"] and consent_status(draft.consent)["terms_accepted"]:
        rows.append(_button(
            "▶ Подтверждаю запуск написания глав",
            f"ll_writer_confirm:{story_id}",
        ))
        message = (
            "📖 Всё готово к написанию глав.\n"
            "Запуск создаст задания для AI-провайдера; возможны расходы "
            "на генерацию текста. Ориентир внутреннего лимита: "
            "до $0.05 за главу, не цена книги для покупателя. "
            "Платёж клиенту здесь не списывается.\n\n"
            "Нажмите кнопку только если хотите начать."
        )
    else:
        message = "❌ Написание пока недоступно.\n"
        if not consent_status(draft.consent)["terms_accepted"]:
            message += "• Сначала примите условия и подтвердите полномочия родителя.\n"
            rows.append(_button("▶ Принять условия", f"ll_terms:{story_id}"))
        if not readiness["ready"]:
            message += "\n".join(f"• {reason}" for reason in readiness["blockers"])
    rows.append(_button("⬅️ К книге", f"ll_book:{story_id}"))
    await callback.message.answer(
        message, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_writer_confirm:"))
async def confirm_writer_start(callback: CallbackQuery) -> None:
    story_id = _id(callback)
    if not _private(callback) or story_id is None:
        await callback.answer("Неверная книга", show_alert=True)
        return
    draft = await _owned(story_id, callback.from_user.id)
    if draft is None:
        await callback.answer("Книга не найдена", show_alert=True)
        return
    if not consent_status(draft.consent)["terms_accepted"]:
        await callback.answer("Сначала примите условия", show_alert=True)
        return
    if not chapter_readiness(draft)["ready"]:
        await callback.answer("Условия запуска изменились. Проверьте книгу.", show_alert=True)
        return
    try:
        ids = await enqueue_sketch_chapters(
            story_id=story_id, owner_id=callback.from_user.id,
        )
    except HTTPException as exc:
        await callback.message.answer(
            "⚠️ Не удалось запустить написание: "
            f"{exc.detail}. Данные книги сохранены.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                _button("⬅️ К книге", f"ll_book:{story_id}"),
            ]),
        )
        await callback.answer()
        return
    await callback.message.answer(
        f"✅ В очередь поставлено глав: {len(ids)}. "
        "Это ещё не готовая рукопись. Проверяйте статус глав в книге.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            _button("📖 Проверить главы", f"ll_manuscript_review:{story_id}"),
            _button("⬅️ К книге", f"ll_book:{story_id}"),
        ]),
    )
    await callback.answer()
