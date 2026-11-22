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
from app.little_legend.delivery_reconciliation import (
    RecoveryAction,
    diagnose_delivery,
    repair_confirmed_projection,
)
from app.little_legend.owned_production import load_owned_production
from app.little_legend.release_manifest_store import get_release_manifest

router = Router(name="little_legend_release_preflight")

_ISSUE_HINTS = {
    "scenes_missing": "Нужно завершить план истории",
    "duplicate_scene_ids": "План истории требует проверки",
    "duplicate_chapters": "Обнаружены повторяющиеся главы",
    "parent_approval_missing": "Утвердите рукопись",
    "hero_missing": "Заполните профиль героя",
    "chapter_missing": "Дождитесь написания всех глав",
    "chapter_unapproved": "Прочитайте и утвердите главы",
    "unexpected_chapter": "Состав глав требует проверки",
    "illustration_job_count_invalid": "Запустите иллюстрации или проверьте их очередь",
    "illustration_incomplete": "Дождитесь завершения иллюстраций",
    "illustration_revision_stale": "Иллюстрации устарели после изменения текста",
    "unexpected_illustration": "Найдена иллюстрация вне плана книги",
    "editorial_approval_missing": "Подтвердите финальную редакторскую проверку",
    "pdf_not_verified": "PDF ещё не собран",
}


def release_issue_hints(codes: list[str]) -> list[str]:
    """Translate technical readiness codes into actionable parent-facing hints."""
    return list(dict.fromkeys(_ISSUE_HINTS.get(code, "Нужна проверка производства") for code in codes))





def release_actions(
    story_id: int, *, ready_for_export: bool, delivery_status: DeliveryStatus | None,
    recovery_action: RecoveryAction | None = None,
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
    if recovery_action == RecoveryAction.REPAIR_PROJECTION:
        rows.append([InlineKeyboardButton(
            text="🔎 Восстановить статус доставки",
            callback_data=f"ll_delivery_reconcile:{story_id}",
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
    recovery_action = None
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
            if status != DeliveryStatus.SENT:
                diagnosis = await diagnose_delivery(
                    owner_id=owner_id, story_id=story_id,
                )
                recovery_action = diagnosis.action
                if recovery_action == RecoveryAction.REPAIR_PROJECTION:
                    message = (
                        "✅ Telegram подтвердил отправку книги, но статус "
                        "в базе не обновился. Можно безопасно восстановить "
                        "статус без повторной отправки."
                    )
                elif recovery_action in {
                    RecoveryAction.MANUAL_REVIEW,
                    RecoveryAction.INCONSISTENT,
                }:
                    message = (
                        "⚠️ Результат отправки требует проверки администратором. "
                        "Повторная отправка отключена."
                    )
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
                hints = release_issue_hints(issues)
                message = (
                    "⏳ Книга ещё не готова к сборке. Что осталось:\n"
                    + "\n".join(f"• {hint}" for hint in hints[:6])
                    + "\n\nВернитесь к этапам книги и нажмите основную кнопку."
                )
    except PermissionError:
        await callback.answer("Книга ещё не готова", show_alert=True)
        return
    lang = await selected_language(callback.from_user)
    keyboard = release_actions(
        story_id, ready_for_export=ready, delivery_status=status,
        recovery_action=recovery_action,
    )
    keyboard.inline_keyboard.insert(-1, [help_button(lang, "release", story_id)])
    await callback.message.answer(
        message + "\n\n" + stage_message(lang, "release"),
        parse_mode="HTML", reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_delivery_reconcile:"))
async def reconcile_delivery_callback(callback: CallbackQuery) -> None:
    """Parent-triggered projection repair, never a Telegram PDF resend."""
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Только в личном чате", show_alert=True)
        return
    owner_id = callback.from_user.id
    if callback.message.chat.id != owner_id:
        await callback.answer("Откройте личный чат с ботом", show_alert=True)
        return
    try:
        story_id = int((callback.data or "").split(":", 1)[1])
        if story_id <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await callback.answer("Неверная книга", show_alert=True)
        return
    try:
        diagnosis = await repair_confirmed_projection(
            owner_id=owner_id, story_id=story_id,
        )
    except PermissionError:
        await callback.answer("Нет доступа к книге", show_alert=True)
        return
    if diagnosis.action == RecoveryAction.CONSISTENT:
        await callback.answer("Статус доставки подтверждён", show_alert=True)
    else:
        await callback.answer(
            "Повторная отправка отключена. Нужна проверка статуса.",
            show_alert=True,
        )
    await callback.message.answer(
        "📘 Вернитесь к книге для просмотра актуального статуса.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="📘 К книге", callback_data=f"ll_book:{story_id}",
            ),
        ]]),
    )
