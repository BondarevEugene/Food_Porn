"""Telegram-native premium photo consent and private photo intake.

Explicit opt-in only. No public image links, no photo bytes in FSM or Neon.
"""
from __future__ import annotations

import logging
import os
from io import BytesIO

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.little_legend.generated_art_store import GeneratedArtS3Settings
from app.little_legend.neon_photo_vault import NeonVaultMetadataRepository
from app.little_legend.neon_premium_photo_consent import NeonPremiumPhotoConsentRepository
from app.little_legend.premium_photo_consent import (
    accept_premium_photo_consent,
    configured_premium_photo_disclosure,
)
from app.little_legend.premium_photo_intake import upload_consented_child_photo
from app.little_legend.private_photo_vault import (
    AuthorizedPrivatePhotoVault,
    S3PrivatePhotoStore,
)
from app.little_legend.secure_vault import MAX_UPLOAD_BYTES

logger = logging.getLogger(__name__)
router = Router(name="little_legend_photo")


class PhotoUpload(StatesGroup):
    waiting = State()


def _story_id(data: str | None) -> int:
    try:
        value = int((data or "").split(":", 1)[1])
    except (IndexError, ValueError) as exc:
        raise PermissionError("Invalid book") from exc
    if value <= 0:
        raise PermissionError("Invalid book")
    return value


def _private_chat(callback: CallbackQuery) -> bool:
    return bool(
        callback.message
        and callback.message.chat.type == "private"
        and callback.message.chat.id == callback.from_user.id
    )


@router.callback_query(F.data.startswith("ll_photo_notice:"))
async def photo_notice(callback: CallbackQuery) -> None:
    if not _private_chat(callback):
        await callback.answer("Open your private chat", show_alert=True)
        return
    try:
        story_id = _story_id(callback.data)
    except PermissionError:
        await callback.answer("Invalid book", show_alert=True)
        return
    disclosure = configured_premium_photo_disclosure()
    if not disclosure.ready:
        await callback.answer("Photo personalization is not available yet", show_alert=True)
        return
    from sqlalchemy import select

    from app.database.session import async_session_maker
    from app.little_legend.vault_registry import stories_table

    async with async_session_maker() as session:
        owned = (await session.execute(select(stories_table.c.id).where(
            stories_table.c.id == story_id,
            stories_table.c.owner_id == callback.from_user.id,
        ))).scalar_one_or_none()
    if owned is None:
        await callback.answer("Book not found", show_alert=True)
        return
    await callback.message.answer(
        disclosure.notice() + "\n\nПодтверждаю, что являюсь родителем "
        "или законным представителем ребёнка.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Согласен(на) на передачу фото",
                callback_data=f"ll_photo_accept:{story_id}",
            )],
            [InlineKeyboardButton(
                text="🚫 Не согласен(на)", callback_data=f"ll_book:{story_id}",
            )],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ll_photo_accept:"))
async def photo_accept(callback: CallbackQuery, state: FSMContext) -> None:
    if not _private_chat(callback):
        await callback.answer("Open your private chat", show_alert=True)
        return
    try:
        story_id = _story_id(callback.data)
        disclosure = configured_premium_photo_disclosure()
        consent = accept_premium_photo_consent(
            provider=disclosure.provider, notice=disclosure.notice(),
            parent_authorized=True, disclosure=disclosure,
        )
        await NeonPremiumPhotoConsentRepository().accept(
            owner_id=callback.from_user.id, story_id=story_id,
            consent=consent,
        )
    except (PermissionError, ValueError):
        await callback.answer("Consent unavailable or book not found", show_alert=True)
        return
    await state.set_state(PhotoUpload.waiting)
    await state.update_data(ll_photo_story_id=story_id)
    await callback.message.answer(
        "📷 Отправьте одно фото ребёнка как фотографию в этот чат. "
        "Для отмены используйте /cancel_photo. Максимум 12 МБ."
    )
    await callback.answer()


@router.message(F.text == "/cancel_photo", PhotoUpload.waiting)
async def cancel_photo(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Загрузка фотографии отменена. Согласие можно отозвать в книге.")


@router.message(PhotoUpload.waiting, F.photo)
async def receive_photo(message: Message, state: FSMContext) -> None:
    if not message.from_user or message.chat.type != "private":
        return
    data = await state.get_data()
    story_id = data.get("ll_photo_story_id")
    if not isinstance(story_id, int) or story_id <= 0:
        await state.clear()
        await message.answer("Сессия загрузки истекла.")
        return
    photo = message.photo[-1]
    if photo.file_size and photo.file_size > MAX_UPLOAD_BYTES:
        await message.answer("Фото слишком большое. Максимум 12 МБ.")
        return
    try:
        # Reuse configured private R2 credentials; do not create a public bucket.
        settings = store_settings_from_environment()
        vault = AuthorizedPrivatePhotoVault(
            metadata=NeonVaultMetadataRepository(),
            objects=S3PrivatePhotoStore(settings),
        )
        buffer = BytesIO()
        await message.bot.download(photo, destination=buffer)
        raw = buffer.getvalue()
        if len(raw) > MAX_UPLOAD_BYTES:
            raise ValueError("Image too large")
        await upload_consented_child_photo(
            owner_id=message.from_user.id, story_id=story_id,
            data=raw, vault=vault,
            consents=NeonPremiumPhotoConsentRepository(),
        )
    except (PermissionError, ValueError):
        await message.answer("Фото не принято. Проверьте согласие и формат изображения.")
        return
    except Exception:
        logger.exception("Little Legend private photo intake failed")
        await message.answer("⚠️ Не удалось сохранить фото. Попробуйте позже.")
        return
    await state.clear()
    await message.answer(
        f"✅ Фото сохранено приватно для книги #{story_id}. "
        "Его можно удалить, отозвав согласие в карточке книги."
    )


def store_settings_from_environment() -> GeneratedArtS3Settings:
    keys = (
        "LITTLE_LEGEND_S3_ENDPOINT_URL",
        "LITTLE_LEGEND_S3_BUCKET",
        "LITTLE_LEGEND_S3_REGION",
        "LITTLE_LEGEND_S3_ACCESS_KEY_ID",
        "LITTLE_LEGEND_S3_SECRET_ACCESS_KEY",
    )
    return GeneratedArtS3Settings(*(os.environ.get(key, "") for key in keys))


@router.callback_query(F.data.startswith("ll_photo_withdraw:"))
async def photo_withdraw(callback: CallbackQuery, state: FSMContext) -> None:
    if not _private_chat(callback):
        await callback.answer("Open your private chat", show_alert=True)
        return
    try:
        story_id = _story_id(callback.data)
        await NeonPremiumPhotoConsentRepository().withdraw(
            owner_id=callback.from_user.id, story_id=story_id,
        )
    except PermissionError:
        await callback.answer("Active consent not found", show_alert=True)
        return
    await state.clear()
    await callback.message.answer(
        "🚫 Согласие отозвано. Фотографии поставлены в очередь удаления из R2."
    )
    await callback.answer()
