"""Telegram-native, owner-scoped Little Legend palette picker."""
from __future__ import annotations

from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy import select, update

from app.bot.handlers.wallpaper import language_for, text_for
from app.database.session import async_session_maker
from app.little_legend.order_quotes import order_quotes
from app.little_legend.palette_catalog import book_palette_catalog
from app.little_legend.palette_preview import render_palette_preview
from app.little_legend.router import StoryDraft, stories

router = Router(name="little_legend_palettes")


def _keyboard(items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=title, callback_data=data)]
        for title, data in items
    ])


def _parse(callback: CallbackQuery, parts: int) -> list[str] | None:
    if (callback.message is None or callback.message.chat.type != "private"
            or callback.message.chat.id != callback.from_user.id):
        return None
    pieces = (callback.data or "").split(":")
    if len(pieces) != parts:
        return None
    try:
        story_id = int(pieces[1])
    except ValueError:
        return None
    if story_id <= 0:
        return None
    return pieces


async def _owned(story_id: int, owner_id: int) -> StoryDraft | None:
    async with async_session_maker() as session:
        raw = await session.scalar(select(stories.c.data).where(
            stories.c.id == story_id, stories.c.owner_id == owner_id,
        ))
    return StoryDraft.model_validate_json(raw) if raw is not None else None


@router.callback_query(F.data.startswith("ll_palette:"))
async def choose_palette_group(callback: CallbackQuery) -> None:
    parts = _parse(callback, 2)
    if parts is None:
        await callback.answer("Open your own private chat", show_alert=True)
        return
    story_id = int(parts[1])
    draft = await _owned(story_id, callback.from_user.id)
    if draft is None:
        await callback.answer("Book not found", show_alert=True)
        return
    lang = language_for(callback.from_user)
    catalog = book_palette_catalog()
    buttons = [(group.title, f"ll_pgroup:{story_id}:{group.id}")
               for group in catalog.groups]
    buttons.append((text_for(lang, "⬅️ Моя книга", "⬅️ Моя книга", "⬅️ My book"),
                    f"ll_book:{story_id}"))
    await callback.message.answer(
        text_for(lang, "🎨 Оберіть настрій обкладинки",
                 "🎨 Выберите настроение обложки",
                 "🎨 Choose a cover mood"),
        reply_markup=_keyboard(buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_pgroup:"))
async def choose_palette_color(callback: CallbackQuery) -> None:
    parts = _parse(callback, 3)
    if parts is None:
        await callback.answer("Invalid request", show_alert=True)
        return
    story_id, group_id = int(parts[1]), parts[2]
    if await _owned(story_id, callback.from_user.id) is None:
        await callback.answer("Book not found", show_alert=True)
        return
    group = next((g for g in book_palette_catalog().groups if g.id == group_id), None)
    if group is None:
        await callback.answer("Unknown category", show_alert=True)
        return
    buttons = [(option.title, f"ll_pconfirm:{story_id}:{option.id}")
               for option in group.options]
    buttons.append(("⬅️ Категории / Categories", f"ll_palette:{story_id}"))
    await callback.message.answer(
        f"🎨 {group.title} · 5 вариантов",
        reply_markup=_keyboard(buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_pconfirm:"))
async def confirm_palette_color(callback: CallbackQuery) -> None:
    parts = _parse(callback, 3)
    if parts is None:
        await callback.answer("Invalid request", show_alert=True)
        return
    story_id, palette = int(parts[1]), parts[2]
    draft = await _owned(story_id, callback.from_user.id)
    if draft is None:
        await callback.answer("Book not found", show_alert=True)
        return
    option = next((o for g in book_palette_catalog().groups
                   for o in g.options if o.id == palette), None)
    if option is None:
        await callback.answer("Unknown palette", show_alert=True)
        return
    keyboard = _keyboard([
        ("✅ Подтвердить", f"ll_psave:{story_id}:{palette}"),
        ("⬅️ Изменить", f"ll_palette:{story_id}"),
    ])
    try:
        preview = render_palette_preview(palette=palette, title=draft.title)
    except ValueError:
        await callback.answer("Preview unavailable", show_alert=True)
        return
    await callback.message.answer_photo(
        BufferedInputFile(preview, filename=f"little-legend-{palette}.png"),
        caption=(
            f"🎨 {option.title}\\n"
            "Предпросмотр цветового оформления. Иллюстрации ребёнка "
            "и окончательная обложка появятся в готовой книге."
        ),
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_psave:"))
async def save_palette_color(callback: CallbackQuery) -> None:
    parts = _parse(callback, 3)
    if parts is None:
        await callback.answer("Invalid request", show_alert=True)
        return
    story_id, palette = int(parts[1]), parts[2]
    if palette not in {o.id for g in book_palette_catalog().groups
                       for o in g.options}:
        await callback.answer("Unknown palette", show_alert=True)
        return
    async with async_session_maker() as session:
        raw = await session.scalar(select(stories.c.data).where(
            stories.c.id == story_id,
            stories.c.owner_id == callback.from_user.id,
        ).with_for_update())
        if raw is None:
            await callback.answer("Book not found", show_alert=True)
            return
        quote = await session.scalar(select(order_quotes.c.id).where(
            order_quotes.c.story_id == story_id,
            order_quotes.c.owner_id == callback.from_user.id,
        ).limit(1))
        if quote is not None:
            await callback.answer(
                "Оформление уже зафиксировано. Изменение темы недоступно.",
                show_alert=True,
            )
            return
        draft = StoryDraft.model_validate_json(raw)
        draft.palette = palette
        await session.execute(update(stories).where(
            stories.c.id == story_id,
            stories.c.owner_id == callback.from_user.id,
        ).values(data=draft.model_dump_json(), updated_at=datetime.now(UTC)))
        await session.commit()
    await callback.message.answer(
        "✅ Оформление сохранено. Оно будет применено к вашей книге.",
        reply_markup=_keyboard([("📖 Моя книга", f"ll_book:{story_id}")]),
    )
    await callback.answer()
