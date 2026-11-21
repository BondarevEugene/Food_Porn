"""Telegram release preflight backed by the existing production and manifest gates."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.handlers.little_legend_context_help import (
    help_button,
    selected_language,
    stage_message,
)
from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.owned_production import load_owned_production
from app.little_legend.release_manifest_store import get_release_manifest

router = Router(name="little_legend_release_preflight")


def release_actions(
    story_id: int, *, ready_for_export: bool, delivery_status: DeliveryStatus | None,
) -> InlineKeyboardMarkup:
    """Only offer the next valid step; never bypass server-side gates."""
    rows = []
    if delivery_status is None and ready_for_export:
        rows.append([InlineKeyboardButton(
            text="📘 Подтвердить сборку PDF",
            callback_data=f"ll_prepare:{story_id}",
        )])
    elif delivery_status == DeliveryStatus.READY:
        rows.append([InlineKeyboardButton(
            text="📥 Получить готовый PDF",
            callback_data=f"ll_send:{story_id}",
        )])
    rows.append([InlineKeyboardButton(
        text="📊 Производство книги",
        callback_data=f"ll_checkpoint:{story_id}",
    )])
    rows.append([InlineKeyboardButton(
        text="⬅️ К книге", callback_data=f"ll_book:{story_id}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("ll_release_review:"))
async def show_release_preflight(callback: CallbackQuery) -> None:
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Только в личном чате", show_alert=True)
        return
    try:
        story_id = int((callback.data or "").split(":", 1)[1])
        if story_id <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await callback.answer("Неверная книга", show_alert=True)
        return
    owner_id = callback.from_user.id
    if callback.message.chat.id != owner_id:
        await callback.answer("Откройте личный чат с ботом", show_alert=True)
        return
    try:
        manifest = await get_release_manifest(owner_id=owner_id, story_id=story_id)
        if manifest is not None:
            # A manifest is never an authorization to assemble again.
            status = manifest.status
            if status == DeliveryStatus.READY:
                message = "📘 PDF собран и сохранён. Можно запросить доставку."
            elif status == DeliveryStatus.SENT:
                message = "✅ PDF уже отправлен. Повторная отправка отключена."
            else:
                message = (
                    "⚠️ Доставка уже началась или требует сверки. "
                    "Автоматическая повторная отправка запрещена."
                )
            ready = False
        else:
            production = await load_owned_production(
                owner_id=owner_id, story_id=story_id,
            )
            readiness = production.readiness()
            ready = readiness.ready_for_export
            status = None
            if ready:
                message = (
                    f"📘 Книга готова к сборке: {readiness.total_scenes} сцен, "
                    "главы и иллюстрации проверены, редакционное утверждение получено. "
                    "Сборка использует уже сохранённые материалы, без AI-вызовов."
                )
            else:
                issues = sorted({issue.code for issue in readiness.issues})
                message = (
                    "⏳ Сборка пока недоступна. "
                    "Незакрытые проверки: " + ", ".join(issues[:12])
                )
    except PermissionError:
        await callback.answer("Книга ещё не готова", show_alert=True)
        return
    lang = await selected_language(callback.from_user)
    keyboard = release_actions(
        story_id, ready_for_export=ready, delivery_status=status,
    )
    keyboard.inline_keyboard.insert(-1, [help_button(lang, "release", story_id)])
    await callback.message.answer(
        message + "\n\n" + stage_message(lang, "release"),
        parse_mode="HTML", reply_markup=keyboard,
    )
    await callback.answer()
