"""Create a thoughtful visual gift from one to seven uploaded photographs."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import uuid
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
    WebAppInfo,
)
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.keyboards import add_wayforpay_option
from app.bot.states.wallpaper import WallpaperStates
from app.config import Settings, get_settings
from app.crm.models import GiftPaymentReceipt, GiftPurchase
from app.database.repositories import WallpaperOrderRepository, WayForPayPaymentRepository
from app.services.free_access import has_free_generation_access
from app.services.gift_delivery import deliver_paid_gift
from app.services.gift_drafts import load_gift_draft, store_gift_draft
from app.services.gift_fulfillment import GiftFulfillmentBusy, process_paid_gift_purchase
from app.services.gift_pricing import checkout_price_uah
from app.services.gift_purchases import create_gift_quote
from app.services.goal_story import GoalScenePlanner
from app.services.payment import PaymentService
from app.services.portmone_sandbox import send_portmone_sandbox_offer
from app.services.print_bundle import create_print_bundle
from app.services.replicate_vision_board import ImageSafetyError, ReplicateVisionBoardRenderer
from app.services.stars import OrderRef, create_invoice
from app.services.video_story_plans import VideoTier
from app.services.wallpaper_studio import archive_source_photos
from app.services.wayforpay import WayForPayService, apply_verified_payment

router = Router(name="wallpaper")
logger = logging.getLogger(__name__)

# Безопасный кеш блокировок пользователей с ограничением/очисткой при необходимости
_locks_cache: dict[int, asyncio.Lock] = {}


def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _locks_cache:
        _locks_cache[user_id] = asyncio.Lock()
    return _locks_cache[user_id]


MAX_GIFT_PHOTOS = 7


def text_for(lang: str, uk: str, ru: str, en: str) -> str:
    return {"ru": ru, "en": en}.get(lang, uk)


def gift_keyboard(lang: str, selected: str = "dark") -> InlineKeyboardMarkup:
    styles = (
        ("dark", "🌙 Темна", "🌙 Тёмная", "🌙 Dark"),
        ("light", "☀️ Світла", "☀️ Светлая", "☀️ Light"),
        ("color", "🌈 Кольорова", "🌈 Цветная", "🌈 Color"),
    )
    # This keyboard is used only after the photo and product stages.
    # Never offer to restart photo upload from the style selection step.
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=("✓ " if key == selected else "") + text_for(lang, uk, ru, en),
            callback_data=f"gift_style:{key}",
        ) for key, uk, ru, en in styles],
        [InlineKeyboardButton(
            text=text_for(lang, "⬅️ Головне меню", "⬅️ Главное меню", "⬅️ Main menu"),
            callback_data="back_to_products",
        )],
    ])


def gift_photo_start_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Photo stage: no style or checkout actions."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=text_for(lang, "📷 Додати фото", "📷 Добавить фото", "📷 Add photos"),
            callback_data="gift_five_photos",
        )],
        [InlineKeyboardButton(
            text=text_for(lang, "🏠 Головна", "🏠 Главная", "🏠 Home"),
            callback_data="back_to_products",
        )],
    ])


def safety_recovery_keyboard(lang: str, photo_count: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=text_for(lang, "📷 Інше фото", "📷 Другое фото", "📷 Another photo"),
        callback_data="gift_safety_one_photo",
    )]]
    if photo_count > 1:
        rows.append([InlineKeyboardButton(
            text=text_for(lang, "🖼 Замінити фото", "🖼 Заменить фото", "🖼 Replace photos"),
            callback_data="gift_safety_five_photos",
        )])
    rows.append([InlineKeyboardButton(
        text=text_for(lang, "✍️ Змінити цілі", "✍️ Изменить цели", "✍️ Revise goals"),
        callback_data="gift_safety_goals",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def finish_photos_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=text_for(lang, "Продовжити →", "Продолжить →", "Continue →"),
            callback_data="gift_photos_done",
        )],
    ])


def photo_upload_status(lang: str, count: int, limit: int = MAX_GIFT_PHOTOS) -> str:
    """Short per-photo progress text in the user's chosen language."""
    return text_for(
        lang,
        f"📷 <b>Фото · {count}/{limit}</b>\n"
        + ("Усі фото збережено. Натисніть «Продовжити»." if count >= limit else "Додайте ще фото або перейдіть далі."),
        f"📷 <b>Фото · {count}/{limit}</b>\n"
        + ("Все фото сохранены. Нажмите «Продолжить»." if count >= limit else "Добавьте ещё фото или переходите дальше."),
        f"📷 <b>Photos · {count}/{limit}</b>\n"
        + ("All photos saved. Tap Continue." if count >= limit else "Add another photo or continue."),
    )


def gift_product_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Select the requested deliverables once, after photo upload."""
    choices = (
        ("collage", "🖼️ Лише колаж", "🖼️ Только коллаж", "🖼️ Collage only"),
        ("video", "🎬 Лише відеоісторія", "🎬 Только видеоистория", "🎬 Video only"),
        ("both", "✨ Колаж + відео", "✨ Коллаж + видео", "✨ Collage + video"),
    )
    rows = [
        [InlineKeyboardButton(
            text=text_for(lang, uk, ru, en), callback_data=f"gift_product:{key}"
        )]
        for key, uk, ru, en in choices
    ]
    rows.extend([
        [InlineKeyboardButton(
            text=text_for(lang, "⬅️ До фото", "⬅️ К фото", "⬅️ Photos"),
            callback_data="gift_back_to_photos",
        )],
        [InlineKeyboardButton(
            text=text_for(lang, "🏠 Головна", "🏠 Главная", "🏠 Home"),
            callback_data="back_to_products",
        )],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def video_story_entry_keyboard(settings: Settings, lang: str) -> InlineKeyboardMarkup | None:
    """Use the paid Scene Studio flow; Telegram has no standalone video checkout."""
    if not settings.miniapp_url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=text_for(lang, "🎬 Відкрити Scene Studio", "🎬 Открыть Scene Studio",
                          "🎬 Open Scene Studio"),
            web_app=WebAppInfo(url=settings.miniapp_url),
        ),
    ]])


async def send_video_story_entry(callback: CallbackQuery, state: FSMContext,
                                 settings: Settings) -> None:
    """Previously uploaded photos are archived with the collage, not kept in uploads."""
    data = await state.get_data()
    lang = data.get("ui_lang") or data.get("lang") or language_for(callback.from_user)
    if not settings.miniapp_url:
        await callback.answer(text_for(
            lang, "Майстерня тимчасово недоступна. Спробуйте пізніше.",
            "Мастерская временно недоступна. Попробуйте позже.",
            "Scene Studio is temporarily unavailable. Please try later.",
        ), show_alert=True)
        return
    await callback.message.answer(
        text_for(
            lang,
            "🎬 Ваші готові колажі та збережені фото доступні в Scene Studio. "
            "Відкрийте оплачений колаж, оберіть відеоісторію та її окрему оплату. "
            "Повторно завантажувати фото не потрібно.",
            "🎬 Ваши готовые коллажи и сохранённые фото доступны в Scene Studio. "
            "Откройте оплаченный коллаж и выберите видеоисторию с отдельной оплатой. "
            "Повторно загружать фото не нужно.",
            "🎬 Your completed collages and saved photos are in Scene Studio. "
            "Open your paid collage and select the separately paid video story. "
            "No need to upload photos again.",
        ),
        reply_markup=video_story_entry_keyboard(settings, lang),
    )
    await callback.answer()


@router.callback_query(F.data == "gift_video_plans")
async def show_gift_video_plans(callback: CallbackQuery, state: FSMContext,
                                settings: Settings) -> None:
    await send_video_story_entry(callback, state, settings)


@router.callback_query(F.data.startswith("gift_video_tier:"))
async def choose_gift_video_tier(callback: CallbackQuery, state: FSMContext,
                                 settings: Settings) -> None:
    """Support old inline tariff buttons without promising unavailable 30/60s renders."""
    try:
        VideoTier((callback.data or "").removeprefix("gift_video_tier:"))
    except ValueError:
        await callback.answer("Невідомий тариф / Неизвестный тариф", show_alert=True)
        return
    await send_video_story_entry(callback, state, settings)


@router.callback_query(F.data.in_({"gift_safety_one_photo", "gift_safety_five_photos", "gift_safety_goals"}))
async def recover_blocked_gift(callback: CallbackQuery, state: FSMContext,
                               settings: Settings) -> None:
    data = await state.get_data()
    if not data.get("blocked_input"):
        await callback.answer("Почніть новий подарунок через /start 💛")
        return
    lang = data.get("lang", "uk")
    if callback.data == "gift_safety_goals":
        await state.set_state(WallpaperStates.waiting_for_goals)
        await callback.message.answer(text_for(lang,
                                               "Фото збережені 💛 Напишіть від 5 до 9 оновлених цілей, кожну з нового рядка.",
                                               "Фото сохранены 💛 Напишите от 5 до 9 уточнённых целей, каждую с новой строки.",
                                               "Your photos are saved 💛 Send 5 to 9 revised goals, one per line."))
    else:
        if callback.data == "gift_safety_five_photos" and len(upload_paths(settings, callback.from_user.id)) <= 1:
            await callback.answer("Цей варіант доступний для замовлення з кількома фото.")
            return
        folder = settings.uploads_dir / "wallpapers" / str(callback.from_user.id)
        if folder.exists():
            await asyncio.to_thread(shutil.rmtree, folder)
        await state.update_data(render_job=None, blocked_input=False)
        five = callback.data == "gift_safety_five_photos"
        await state.set_state(WallpaperStates.waiting_for_five_photos if five else
                              WallpaperStates.waiting_for_photo)
        await callback.message.answer(text_for(lang,
                                               "Цілі й стиль збережені 💛 Надішліть від 1 до 7 нових фото й натисніть «Готово»." if five else
                                               "Цілі й стиль збережені 💛 Надішліть інше фото.",
                                               "Цели и стиль сохранены 💛 Пришлите от 1 до 7 новых фото и нажмите «Готово»." if five else
                                               "Цели и стиль сохранены 💛 Пришлите другое фото.",
                                               "Your goals and style are saved 💛 Send 1 to 7 new photos and tap Done." if five else
                                               "Your goals and style are saved 💛 Send another photo."))
    await callback.answer()


def language_for(user: object) -> str:
    code = (getattr(user, "language_code", "") or "").lower()
    return "ru" if code.startswith("ru") else "en" if code.startswith("en") else "uk"


def upload_paths(settings: Settings, user_id: int) -> list[Path]:
    folder = settings.uploads_dir / "wallpapers" / str(user_id)
    portrait = folder / "portrait.jpg"
    if portrait.is_file():
        return [portrait]
    return sorted(folder.glob("photo_*.jpg"), key=lambda path: int(path.stem.removeprefix("photo_")))


def parse_five_goals(text: str) -> list[str]:
    """Require five to nine customer goals and keep their original wording."""
    goals = [re.sub(r"^\s*[1-9][.)]\s*", "", line).strip()
             for line in text.splitlines() if line.strip()]
    if not 5 <= len(goals) <= 9 or any(not goal for goal in goals):
        raise ValueError("Send five to nine non-empty goals, one per line")
    return goals


def save_photo(payload: bytes, destination: Path) -> None:
    with Image.open(BytesIO(payload)) as image:
        image.verify()
    with Image.open(BytesIO(payload)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.thumbnail((3000, 3000), Image.Resampling.LANCZOS)
        if min(image.size) < 300:
            raise ValueError("Image too small")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{uuid.uuid4().hex}.jpg")
        try:
            image.save(temporary, "JPEG", quality=93, optimize=True)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)


def make_preview(image_path: Path) -> Path:
    preview = image_path.with_name(f"preview_{image_path.stem}.jpg")
    with Image.open(image_path) as source:
        image = source.convert("RGBA")
    overlay = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(overlay)
    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if not font_path.exists():
        font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = (ImageFont.truetype(str(font_path), max(17, image.width // 44))
            if font_path.exists() else ImageFont.load_default())
    label = "PREVIEW"
    bbox = draw.textbbox((0, 0), label, font=font)
    margin = max(22, image.width // 28)
    x = image.width - (bbox[2] - bbox[0]) - margin
    y = image.height - (bbox[3] - bbox[1]) - margin
    draw.text((x, y), label, font=font, fill=(255, 255, 255, 115),
              stroke_width=1, stroke_fill=(20, 15, 10, 125))
    Image.alpha_composite(image, overlay).convert("RGB").save(
        preview, "JPEG", quality=92, subsampling=0, optimize=True)
    return preview


async def start_wallpaper_from_start(message: Message, state: FSMContext,
                                     settings: Settings | None = None, user_id: int | None = None,
                                     lang: str | None = None) -> None:
    settings = settings or get_settings()
    user_id = user_id or message.from_user.id
    lang = lang or language_for(message.from_user)
    selected = (await state.get_data()).get("lang_selected", False)
    await state.clear()
    await state.update_data(ui_lang=lang, lang=lang, lang_selected=selected, style="dark")
    folder = settings.uploads_dir / "wallpapers" / str(user_id)
    if folder.exists():
        shutil.rmtree(folder)
    await state.set_state(WallpaperStates.waiting_for_photo)
    await message.answer(text_for(
        lang,
        "✨ <b>Ваша історія бажань</b>\n\n<b>Крок 1 із 3 · Фото</b>\n"
        "Надішліть від 1 до 7 фотографій. Можна почати з однієї, "
        "а додаткові додати кнопкою нижче.\n\n"
        "Потім оберете формат, цілі та стиль.",
        "✨ <b>Ваша история желаний</b>\n\n<b>Шаг 1 из 3 · Фото</b>\n"
        "Пришлите от 1 до 7 фотографий. Можно начать с одной, "
        "а остальные добавить кнопкой ниже.\n\n"
        "Затем выберете формат, цели и стиль.",
        "✨ <b>Your wish story</b>\n\n<b>Step 1 of 3 · Photos</b>\n"
        "Send 1–7 photos. Start with one and add others using the button below.\n\n"
        "Then choose the format, goals and style.",
    ), parse_mode="HTML", reply_markup=gift_photo_start_keyboard(lang))


@router.message(F.text == "/resume")
async def resume_saved_photos(message: Message, state: FSMContext, settings: Settings,
                              session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
    """Recover uploads after the bot restarts and its in-memory FSM is lost."""
    photos = upload_paths(settings, message.from_user.id)
    if not 1 <= len(photos) <= MAX_GIFT_PHOTOS:
        await message.answer("Не нашёл сохранённый комплект фото. Начните новый подарок через /start 💛")
        return
    lang = language_for(message.from_user)
    await state.clear()
    draft = await load_gift_draft(session_factory, message.from_user.id) if session_factory else None
    # Never reuse a previous product choice for a different batch of photos.
    if draft and set(draft.photo_paths or []) != {str(photo) for photo in photos}:
        draft = None
    stored_choice = draft.product_choice if draft and draft.product_choice in {"collage", "video", "both"} else None
    stored_goals = list(draft.goals or []) if draft else []
    await state.update_data(
        ui_lang=lang, lang=lang, style=draft.style if draft else "dark",
        gift_product=stored_choice, goals=stored_goals,
    )
    if stored_choice:
        await state.set_state(WallpaperStates.waiting_for_goals)
        await message.answer(text_for(
            lang,
            "Фото та вибір продукту відновлено 💛 Надішліть цілі, щоб продовжити.",
            "Фото и выбор продукта восстановлены 💛 Пришлите цели, чтобы продолжить.",
            "Photos and product selection restored 💛 Send your goals to continue.",
        ), reply_markup=gift_keyboard(lang, draft.style if draft else "dark"))
        return
    await state.set_state(WallpaperStates.waiting_for_product)
    await message.answer(
        text_for(lang,
                 f"Збережено {len(photos)} фото 💛 Оберіть продукт, щоб продовжити.",
                 f"Сохранено {len(photos)} фото 💛 Выберите продукт для продолжения.",
                 f"Saved {len(photos)} photos 💛 Choose your product to continue."),
        reply_markup=gift_product_keyboard(lang),
    )


@router.callback_query(F.data.startswith("gift_style:"))
async def select_gift_style(callback: CallbackQuery, state: FSMContext) -> None:
    style = (callback.data or "").removeprefix("gift_style:")
    current = await state.get_state()
    allowed = {WallpaperStates.waiting_for_photo.state,
               WallpaperStates.waiting_for_five_photos.state,
               WallpaperStates.waiting_for_goals.state}
    if style not in {"dark", "light", "color"} or current not in allowed:
        await callback.answer("Почніть новий подарунок через /start 💛")
        return
    data = await state.get_data()
    if data.get("style") != style:
        await state.update_data(style=style, render_job=None)
    label = {
        "dark": ("темну", "тёмную", "dark"),
        "light": ("світлу", "светлую", "light"),
        "color": ("кольорову", "цветную", "colorful"),
    }[style]
    lang = data.get("lang", "uk")
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=gift_keyboard(lang, style))
        except Exception:
            logger.debug("Could not update gift style buttons for user %s", callback.from_user.id)
    await callback.answer(text_for(lang,
                                   f"Обрав {label[0]} атмосферу 💛",
                                   f"Выбрал {label[1]} атмосферу 💛",
                                   f"Selected the {label[2]} atmosphere 💛"))


@router.callback_query(F.data == "start_wallpaper_flow")
async def start_wallpaper(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if callback.message:
        await start_wallpaper_from_start(
            callback.message, state, settings,
            user_id=callback.from_user.id, lang=language_for(callback.from_user),
        )
    await callback.answer()


@router.callback_query(F.data == "gift_five_photos", WallpaperStates.waiting_for_photo)
async def start_five_photo_gift(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(WallpaperStates.waiting_for_five_photos)
    await state.update_data(gift_upload_status_message_id=None)
    await callback.message.answer(text_for(
        data.get("lang", "uk"),
        "📷 <b>Крок 1 із 3 · Додайте фото</b>\nДо 7 фото — альбомом або по черзі. "
        "Після завантаження натисніть «Продовжити».",
        "📷 <b>Шаг 1 из 3 · Добавьте фото</b>\nДо 7 фото — альбомом или по одному. "
        "После загрузки нажмите «Продолжить».",
        "📷 <b>Step 1 of 3 · Add photos</b>\nUp to 7 photos in an album or separately. "
        "Tap Continue when ready.",
    ), reply_markup=finish_photos_keyboard(data.get("lang", "uk")))
    await callback.answer()


@router.callback_query(F.data == "gift_photos_done", WallpaperStates.waiting_for_five_photos)
async def finish_gift_photos(callback: CallbackQuery, state: FSMContext, settings: Settings,
                             session_factory: async_sessionmaker[AsyncSession]) -> None:
    user_id = callback.from_user.id
    async with get_user_lock(user_id):
        count = len(upload_paths(settings, user_id))
        if not 1 <= count <= MAX_GIFT_PHOTOS:
            await callback.answer("Надішліть від 1 до 7 фото 💛")
            return
        data = await state.get_data()
        await state.update_data(gift_product=None, gift_upload_status_message_id=None)
        await state.set_state(WallpaperStates.waiting_for_product)
        if session_factory is not None:
            try:
                await store_gift_draft(
                    session_factory, user_id=user_id, product_choice=None,
                    goals=data.get("goals"), photo_paths=upload_paths(settings, user_id),
                    style=data.get("style", "dark"), language=data.get("lang", "uk"),
                    stage="product",
                )
            except Exception:
                logger.exception("Could not persist gift draft for %s", user_id)
    await callback.answer()
    await callback.message.answer(
        text_for(data.get("lang", "uk"),
                 "Фото збережено 💛 Оберіть, що створити:",
                 "Фото сохранены 💛 Выберите, что создать:",
                 "Photos saved 💛 Choose what to create:"),
        reply_markup=gift_product_keyboard(data.get("lang", "uk")),
    )


@router.callback_query(F.data.startswith("gift_product:"))
async def select_gift_product(callback: CallbackQuery, state: FSMContext,
                              session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
    product = (callback.data or "").removeprefix("gift_product:")
    if product not in {"collage", "video", "both"} or (
        await state.get_state()
    ) != WallpaperStates.waiting_for_product.state:
        await callback.answer("Почніть новий подарунок через /start 💛", show_alert=True)
        return
    data = await state.get_data()
    await state.update_data(gift_product=product)
    await state.set_state(WallpaperStates.waiting_for_goals)
    if session_factory is not None:
        try:
            await store_gift_draft(
                session_factory, user_id=callback.from_user.id, product_choice=product,
                goals=data.get("goals"), photo_paths=upload_paths(get_settings(), callback.from_user.id),
                style=data.get("style", "dark"), language=data.get("lang", "uk"),
                stage="goals",
            )
        except Exception:
            logger.exception("Could not persist selected gift product for %s", callback.from_user.id)
    await callback.answer()
    goals_saved = isinstance(data.get("goals"), list) and 5 <= len(data["goals"]) <= 9
    if goals_saved:
        await callback.message.answer(text_for(
            data.get("lang", "uk"),
            "Вибір збережено 💛 Цілі вже є. Надішліть їх повторно, якщо хочете змінити.",
            "Выбор сохранён 💛 Цели уже есть. Пришлите их повторно, если хотите изменить.",
            "Choice saved 💛 Your goals are saved. Resend them only to change them.",
        ), reply_markup=gift_keyboard(data.get("lang", "uk"), data.get("style", "dark")))
    else:
        await callback.message.answer(text_for(
            data.get("lang", "uk"),
            "Вибір збережено 💛 Надішліть 5–9 цілей, кожну з нового рядка. Стиль можна обрати нижче.",
            "Выбор сохранён 💛 Пришлите 5–9 целей, каждую с новой строки. Стиль можно выбрать ниже.",
            "Choice saved 💛 Send 5–9 goals, one per line. Choose the style below.",
        ), reply_markup=gift_keyboard(data.get("lang", "uk"), data.get("style", "dark")))


@router.callback_query(F.data == "gift_photos_done")
async def finish_gift_photos_outside_upload(callback: CallbackQuery, state: FSMContext,
                                            settings: Settings) -> None:
    """Old inline buttons may outlive FSM state or a Railway restart."""
    count = len(upload_paths(settings, callback.from_user.id))
    lang = (await state.get_data()).get("lang") or language_for(callback.from_user)
    if count:
        await callback.message.answer(text_for(
            lang,
            f"Знайдено {count} фото. Для продовження після перезапуску надішліть /resume.",
            f"Найдено {count} фото. Чтобы продолжить после перезапуска, отправьте /resume.",
            f"Found {count} photos. Send /resume to continue after a restart.",
        ))
    else:
        await callback.message.answer(text_for(
            lang,
            "Фото не знайдені. Почніть нову карту бажань через /start.",
            "Фотографии не найдены. Начните новую карту желаний через /start.",
            "No photos found. Start a new wish collage with /start.",
        ))
    await callback.answer()


@router.message(WallpaperStates.waiting_for_photo, F.photo | F.document)
async def collect_photo(message: Message, state: FSMContext, settings: Settings,
                        session_factory: async_sessionmaker[AsyncSession]) -> None:
    data = await state.get_data()
    lang = data.get("lang", "uk")
    if message.document and not (message.document.mime_type or "").startswith("image/"):
        await message.answer(text_for(lang, "Надішліть фото людини, якій хочете зробити подарунок.",
                                      "Пришлите фото человека, которому хотите сделать подарок.",
                                      "Send a photo of the gift recipient."))
        return
    photo = message.photo[-1] if message.photo else message.document
    if photo.file_size and photo.file_size > settings.max_upload_mb * 1024 * 1024:
        await message.answer("Фото перевищує допустимий розмір.")
        return
    source = await message.bot.get_file(photo.file_id)
    payload = BytesIO()
    await message.bot.download(source, destination=payload)
    if payload.tell() > settings.max_upload_mb * 1024 * 1024:
        await message.answer("Фото перевищує допустимий розмір.")
        return
    destination = settings.uploads_dir / "wallpapers" / str(message.from_user.id) / "portrait.jpg"
    try:
        await asyncio.to_thread(save_photo, payload.getvalue(), destination)
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        await message.answer("Фото не вдалося прочитати. Надішліть інше.")
        return
    await state.update_data(render_job=None, blocked_input=False)
    if message.caption and not data.get("goals"):
        try:
            await state.update_data(goals=parse_five_goals(message.caption))
        except ValueError:
            await message.answer(text_for(lang,
                                          "Фото отримав 💛 Тепер надішліть від 5 до 9 цілей одним повідомленням, по одній на рядок.",
                                          "Фото получил 💛 Теперь пришлите от 5 до 9 целей одним сообщением, по одной на строку.",
                                          "Photo received 💛 Please send your 5 to 9 goals in one message, one per line."))
    await state.update_data(gift_product=None)
    await state.set_state(WallpaperStates.waiting_for_product)
    if session_factory is not None:
        try:
            current = await state.get_data()
            await store_gift_draft(
                session_factory, user_id=message.from_user.id, product_choice=None,
                goals=current.get("goals"), photo_paths=upload_paths(settings, message.from_user.id),
                style=current.get("style", "dark"), language=lang, stage="product",
            )
        except Exception:
            logger.exception("Could not persist single-photo gift draft")
    await message.answer(text_for(
        lang,
        "Фото збережено 💛 Оберіть, що створити:",
        "Фото сохранено 💛 Выберите, что создать:",
        "Photo saved 💛 Choose what to create:",
    ), reply_markup=gift_product_keyboard(lang))

@router.message(WallpaperStates.waiting_for_five_photos, F.photo | F.document)
async def collect_five_photos(message: Message, state: FSMContext, settings: Settings,
                              session_factory: async_sessionmaker[AsyncSession]) -> None:
    user_id = message.from_user.id
    async with get_user_lock(user_id):
        data = await state.get_data()
        lang = data.get("lang", "uk")
        count = len(upload_paths(settings, user_id))
        if count >= MAX_GIFT_PHOTOS:
            return
        if message.document and not (message.document.mime_type or "").startswith("image/"):
            await message.answer(
                text_for(lang, "Надішліть зображення, будь ласка.", "Пришлите изображение, пожалуйста.",
                         "Please send an image."))
            return
        photo = message.photo[-1] if message.photo else message.document
        if photo.file_size and photo.file_size > settings.max_upload_mb * 1024 * 1024:
            await message.answer(text_for(lang, "Фото завелике.", "Фото слишком большое.", "The photo is too large."))
            return
        source = await message.bot.get_file(photo.file_id)
        payload = BytesIO()
        await message.bot.download(source, destination=payload)
        if payload.tell() > settings.max_upload_mb * 1024 * 1024:
            await message.answer(text_for(lang, "Фото завелике.", "Фото слишком большое.", "The photo is too large."))
            return
        name = f"photo_{message.message_id}.jpg"
        destination = settings.uploads_dir / "wallpapers" / str(user_id) / name
        try:
            await asyncio.to_thread(save_photo, payload.getvalue(), destination)
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
            await message.answer(
                text_for(lang, "Фото не читається. Спробуйте інше.", "Фото не читается. Попробуйте другое.",
                         "I can't read that photo. Please try another."))
            return
        await state.update_data(render_job=None, blocked_input=False)
        if message.caption and not data.get("goals"):
            try:
                await state.update_data(goals=parse_five_goals(message.caption))
            except ValueError:
                pass
        status = photo_upload_status(lang, count + 1)
        previous_id = data.get("gift_upload_status_message_id")
        if type(previous_id) is int:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=previous_id,
                    text=status,
                    reply_markup=finish_photos_keyboard(lang),
                )
                return
            except Exception:
                logger.info("Photo progress message could not be updated; sending a new one")
        response = await message.answer(
            status, reply_markup=finish_photos_keyboard(lang),
        )
        response_id = getattr(response, "message_id", None)
        if type(response_id) is int:
            await state.update_data(gift_upload_status_message_id=response_id)


@router.message(WallpaperStates.waiting_for_product)
async def waiting_for_product_notice(message: Message, state: FSMContext) -> None:
    lang = (await state.get_data()).get("lang", "uk")
    await message.answer(text_for(
        lang,
        "Фото збережені 💛 Спочатку оберіть продукт кнопкою нижче.",
        "Фото сохранены 💛 Сначала выберите продукт кнопкой ниже.",
        "Your photos are saved 💛 Choose a product using the buttons below first.",
    ), reply_markup=gift_product_keyboard(lang))


@router.message(WallpaperStates.waiting_for_five_photos)
async def waiting_for_five_notice(message: Message, state: FSMContext) -> None:
    lang = (await state.get_data()).get("lang", "uk")
    await message.answer(text_for(lang,
                                  "Чекаю фото 💛 Якщо хочете почати спочатку, надішліть /start.",
                                  "Жду фотографии 💛 Если хотите начать заново, отправьте /start.",
                                  "I'm waiting for photos 💛 Send /start to begin again."))


@router.message(WallpaperStates.waiting_for_photo, F.text)
async def goals_before_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        goals = parse_five_goals(message.text or "")
    except ValueError:
        await message.answer(text_for(data.get("lang", "uk"),
                                      "Напишіть від 5 до 9 цілей, кожну з нового рядка, або спочатку надішліть фото 💛",
                                      "Напишите от 5 до 9 целей, каждую с новой строки, либо сначала пришлите фото 💛",
                                      "Send 5 to 9 goals, one per line, or send the photo first 💛"))
        return
    if data.get("goals") != goals:
        await state.update_data(render_job=None, blocked_input=False)
    await state.update_data(goals=goals)
    await message.answer(text_for(
        data.get("lang", "uk"), "Дякую, усі від 5 до 9 цілей зберіг 💛 Тепер надішліть фото.",
        "Спасибо, все от 5 до 9 целей сохранил 💛 Теперь пришлите фото.",
        "I have your 5 to 9 goals 💛 Now send the photo.",
    ))


@router.message(WallpaperStates.waiting_for_goals, F.text)
async def collect_goals(message: Message, state: FSMContext, settings: Settings,
                        session_factory: async_sessionmaker[AsyncSession]) -> None:
    data = await state.get_data()
    try:
        goals = parse_five_goals(message.text or "")
    except ValueError:
        await message.answer(text_for(data.get("lang", "uk"),
                                      "Потрібні саме від 5 до 9 цілей: кожна з нового рядка. Спробуйте ще раз 💛",
                                      "Нужны именно от 5 до 9 целей: каждая с новой строки. Попробуйте ещё раз 💛",
                                      "Please send exactly 5 to 9 goals, one per line 💛"))
        return
    if data.get("blocked_input") and data.get("goals") == goals:
        await message.answer(text_for(data.get("lang", "uk"),
                                      "Ці фото й цілі вже не пройшли перевірку. Оберіть інше фото або уточніть цілі 💛",
                                      "Эти фото и цели уже не прошли проверку. Выберите другое фото или уточните цели 💛",
                                      "These photos and goals were already declined. Choose another photo or revise the goals 💛"),
                             reply_markup=safety_recovery_keyboard(data.get("lang", "uk"),
                                                                   len(upload_paths(settings, message.from_user.id))))
        return
    if data.get("goals") != goals:
        await state.update_data(render_job=None, blocked_input=False)
    await state.update_data(goals=goals)
    if session_factory is not None and data.get("gift_product") in {"collage", "video", "both"}:
        try:
            await store_gift_draft(
                session_factory, user_id=message.from_user.id,
                product_choice=data["gift_product"], goals=goals,
                photo_paths=upload_paths(settings, message.from_user.id),
                style=data.get("style", "dark"), language=data.get("lang", "uk"),
                stage="ready",
            )
        except Exception:
            logger.exception("Could not persist gift goals for %s", message.from_user.id)
    if data.get("gift_product") in {"video", "both"} or (
        settings.gift_unified_checkout_enabled and data.get("gift_product") == "collage"
    ):
        lang = data.get("lang", "uk")
        if session_factory is None:
            await message.answer(text_for(
                lang,
                "Замовлення не вдалося зберегти. Спробуйте пізніше.",
                "Не удалось сохранить заказ. Попробуйте позже.",
                "Could not save the order. Please try again later.",
            ))
            return
        try:
            quote = await create_gift_quote(
                session_factory, settings=settings, user_id=message.from_user.id,
                choice=data["gift_product"], goals=goals,
                photo_paths=upload_paths(settings, message.from_user.id),
                style=data.get("style", "dark"),
            )
        except ValueError:
            await message.answer(text_for(
                lang,
                "🎬 Цілі та фото збережені, але тариф відео ще не налаштовано. "
                "Оплату не запитуємо.",
                "🎬 Цели и фото сохранены, но тариф видео ещё не настроен. "
                "Оплату не запрашиваем.",
                "🎬 Goals and photos saved, but video pricing is not configured. "
                "No payment will be requested.",
            ))
            return
        except Exception:
            logger.exception("Could not quote gift purchase for %s", message.from_user.id)
            await message.answer(text_for(
                lang,
                "Не вдалося зберегти розрахунок замовлення. Оплату не запитуємо.",
                "Не удалось сохранить расчёт заказа. Оплату не запрашиваем.",
                "Could not save the order quote. No payment will be requested.",
            ))
            return
        await state.update_data(gift_quote_id=quote.id)
        summary = (
            f"Коллаж: {quote.collage_amount:.2f} UAH; "
            f"Видео: {quote.video_amount:.2f} UAH; "
            f"Итого: {quote.total_amount:.2f} UAH."
        )
        if settings.gift_unified_checkout_enabled:
            wayforpay = WayForPayService(settings)
            if wayforpay.ready:
                try:
                    async with session_factory() as session:
                        _, checkout_url = await wayforpay.create_checkout(
                            session,
                            telegram_user_id=message.from_user.id,
                            product="gift_purchase",
                            reference_id=quote.id,
                            description=f"Food Porn gift {quote.product_choice} #{quote.id[:8]}",
                            amount_override=quote.total_amount,
                        )
                except Exception:
                    logger.exception("Could not create unified gift payment for %s", quote.id)
                else:
                    await message.answer(text_for(
                        lang,
                        f"✨ Замовлення № {quote.id[:8]}. {summary} "
                        "Оплатіть один раз — файли надійдуть після підтвердження.",
                        f"✨ Заказ № {quote.id[:8]}. {summary} "
                        "Оплатите один раз — файлы поступят после подтверждения.",
                        f"✨ Order #{quote.id[:8]}. {summary} "
                        "Pay once and receive files after confirmation.",
                    ), reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text=text_for(lang, "💳 Оплатити замовлення", "💳 Оплатить заказ", "💳 Pay for order"),
                            url=checkout_url,
                        )],
                        [InlineKeyboardButton(
                            text=text_for(lang, "🔄 Перевірити оплату", "🔄 Проверить оплату", "🔄 Check payment"),
                            callback_data=f"gift_purchase_status:{quote.id}",
                        )],
                    ]))
                    return
        await message.answer(text_for(
            lang,
            f"🎬 Розрахунок № {quote.id[:8]} збережено. {summary} "
            "Оплата зараз недоступна. Кошти не списані.",
            f"🎬 Расчёт № {quote.id[:8]} сохранён. {summary} "
            "Оплата сейчас недоступна. Деньги не списаны.",
            f"🎬 Quote #{quote.id[:8]} saved. {summary} "
            "Payment is not currently available. No charge has been made.",
        ))
        return
    await state.set_state(WallpaperStates.generating)
    await generate_wallpapers(message, state, settings, session_factory)


@router.callback_query(F.data.startswith("gift_purchase_status:"))
async def verify_gift_purchase_callback(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    purchase_id = (callback.data or "").removeprefix("gift_purchase_status:")
    if not re.fullmatch(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", purchase_id):
        await callback.answer("Некоректний номер замовлення.", show_alert=True)
        return
    async with session_factory() as session:
        purchase = await session.get(GiftPurchase, purchase_id)
        if purchase is None or purchase.telegram_user_id != callback.from_user.id:
            await callback.answer("Замовлення не знайдено.", show_alert=True)
            return
        paid = await session.get(GiftPaymentReceipt, purchase_id) is not None
        attempt = await WayForPayPaymentRepository(session).latest_for_product(
            "gift_purchase", purchase_id, callback.from_user.id,
        )
        if attempt is not None and attempt.test_mode:
            await callback.answer(
                "Тестову оплату збережено. Платний рендер вимкнено.",
                show_alert=True,
            )
            return
        if not paid:
            if attempt is None:
                await callback.answer("Оплату ще не знайдено.", show_alert=True)
                return
            service = WayForPayService(settings)
            try:
                verified_payload = await service.check_status(attempt)
                paid = await apply_verified_payment(session, attempt, verified_payload)
            except Exception:
                logger.exception("Could not verify gift purchase %s", purchase_id)
                await callback.answer("Платіж ще не підтверджено.", show_alert=True)
                return
    if not paid:
        await callback.answer("Платіж ще не підтверджено.", show_alert=True)
        return
    await callback.answer("Оплату підтверджено 💛")
    try:
        await process_paid_gift_purchase(session_factory, settings, purchase_id)
        await deliver_paid_gift(session_factory, callback.bot, purchase_id)
    except GiftFulfillmentBusy:
        await callback.message.answer(
            "✨ Відео або колаж вже створюється. Перевірте статус трохи пізніше."
        )
    except Exception:
        logger.exception("Could not resume paid gift %s", purchase_id)
        await callback.message.answer(
            "Оплату отримано, але видача затримується. "
            "Скористайтеся /paysupport та вкажіть номер замовлення."
        )


@router.message(WallpaperStates.waiting_for_goals)
async def waiting_for_goals_notice(message: Message, state: FSMContext) -> None:
    await message.answer(text_for((await state.get_data()).get("lang", "uk"),
                                  "Фото вже є 💛 Надішліть від 5 до 9 цілей текстом.",
                                  "Фото уже есть 💛 Пришлите от 5 до 9 целей текстом.",
                                  "I have your photos 💛 Please send the 5 to 9 goals as text."))


@router.message(WallpaperStates.generating)
async def processing_notice(message: Message) -> None:
    await message.answer("✨ Я вже працюю над подарунком. Зачекайте трохи, будь ласка.")


def prepare_share_photo(mobile: Path) -> Path:
    """Telegram-ready copy that recipients can view in chat without opening a file."""
    shared = mobile.with_name("share.jpg")
    with Image.open(mobile) as original:
        original.convert("RGB").save(shared, "JPEG", quality=90, optimize=True)
    return shared


async def _send_full(message: Message, mobile: Path, desktop: Path, lang: str = "uk") -> None:
    shared = await asyncio.to_thread(prepare_share_photo, mobile)
    await message.answer_photo(FSInputFile(str(shared)), caption=text_for(
        lang, "Готово 💛 Перешліть це фото близькій людині — нехай усміхнеться.",
        "Готово 💛 Перешлите это фото близкому человеку — пусть улыбнётся.",
        "All set 💛 Forward this picture to make someone smile.",
    ))
    await message.answer_document(FSInputFile(str(mobile)), caption=text_for(
        lang, "Подарунок для телефону · 1080×1920 💛",
        "Подарок для телефона · 1080×1920 💛", "Gift for a phone · 1080×1920 💛",
    ))
    await message.answer_document(FSInputFile(str(desktop)), caption=text_for(
        lang, "Подарунок для комп’ютера · 1920×1080 💛",
        "Подарок для компьютера · 1920×1080 💛", "Gift for a computer · 1920×1080 💛",
    ))


async def generate_wallpapers(message: Message, state: FSMContext, settings: Settings,
                              session_factory: async_sessionmaker[AsyncSession]) -> None:
    data = await state.get_data()
    if data.get("gift_product") in {"video", "both"}:
        raise RuntimeError("Video or bundle selection cannot use collage-only checkout")
    selected = data.get("lang_selected", False)
    photos = upload_paths(settings, message.from_user.id)
    goals = data.get("goals")
    if not 1 <= len(photos) <= MAX_GIFT_PHOTOS:
        await state.set_state(WallpaperStates.waiting_for_photo)
        await message.answer("Не знайшов фотографію. Надішліть її ще раз, будь ласка.")
        return
    if not goals or not 5 <= len(goals) <= 9:
        await state.set_state(WallpaperStates.waiting_for_goals)
        await message.answer(text_for(data.get("lang", "uk"),
                                      "Ще потрібно від 5 до 9 ваших цілей, по одній на рядок 💛",
                                      "Ещё нужны от 5 до 9 ваших целей, по одной на строку 💛",
                                      "I still need your 5 to 9 goals, one per line 💛"))
        return
    lang = data.get("lang", "uk")
    free_access = await has_free_generation_access(
        message.from_user.id, getattr(message.from_user, "username", None), settings, session_factory)
    if not free_access and settings.gift_price_stars < 1:
        await state.set_state(WallpaperStates.waiting_for_goals)
        await message.answer(text_for(lang,
                                      "Оплата недоступна, а для цього акаунта безкоштовний доступ не налаштовано. Фото й цілі збережено 💛",
                                      "Оплата недоступна, а для этого аккаунта бесплатный доступ не настроен. Фото и цели сохранены 💛",
                                      "Payment is unavailable and this account has no free access. Your photos and goals are saved 💛"))
        return
    notice = await message.answer(text_for(
        lang, "Фото отримав 💛 Підбираю теплу історію й створюю подарунок. Це може зайняти кілька хвилин.",
        "Фото получил 💛 Подбираю тёплую историю и создаю подарок. Это может занять несколько минут.",
        "Got the photo 💛 I’m creating your gift. It may take a few minutes.",
    ), reply_markup=ReplyKeyboardRemove())
    try:
        job = data.get("render_job")
        style = data.get("style", "dark")
        if style not in {"dark", "light", "color"}:
            style = "dark"
        if not isinstance(job, dict) or job.get("goals") != goals or job.get("style") != style or not re.fullmatch(
                r"[0-9a-f]{32}", str(job.get("id", ""))):
            job_id = uuid.uuid4().hex
            planner = GoalScenePlanner(settings)
            if hasattr(planner, "set_tracking_context"):
                planner.set_tracking_context(user_id=message.from_user.id, order_id=job_id)
            plan = await planner.plan(photos=photos, goals=goals, lang=lang)
            job = {
                "id": job_id, "goals": list(goals), "style": style,
                "assignments": list(plan.assignments), "scenes": list(plan.scenes),
                "plan_cost_usd": str(plan.ai_cost_usd),
            }
            await state.update_data(render_job=job)
        ai_concept_cost = Decimal(job["plan_cost_usd"])
        render_dir = settings.generated_dir / "wallpapers" / str(message.from_user.id) / job["id"]
        archived_sources = await asyncio.to_thread(archive_source_photos, photos, render_dir)
        renderer = ReplicateVisionBoardRenderer(
            output_dir=render_dir, model=settings.wallpaper_image_model,
            quality=settings.wallpaper_image_quality)
        if hasattr(renderer, "set_tracking_context"):
            renderer.set_tracking_context(user_id=message.from_user.id, order_id=job["id"])
        formats = await renderer.generate_goal_story(
            user_id=message.from_user.id, photo_paths=photos, goals=goals,
            assignments=job["assignments"], scenes=job["scenes"], style=style,
        )
        mobile, desktop = formats["mobile"], formats["desktop"]
        raw_mobile = formats.get("raw_mobile", mobile)
        raw_desktop = formats.get("raw_desktop", desktop)
        preview = await asyncio.to_thread(make_preview, mobile)
        for photo in photos:
            try:
                photo.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove uploaded photo for user %s", message.from_user.id)
    except ImageSafetyError as exc:
        logger.warning("Image check blocked stage %s at %s for user %s; categories=%s request_id=%s",
                       exc.scene_number, exc.stage, message.from_user.id,
                       getattr(exc, "categories", ()), getattr(exc, "request_id", None))
        await state.set_state(WallpaperStates.waiting_for_goals)
        if exc.stage == "output":
            await message.answer(text_for(lang,
                                          "Один із сюжетів не пройшов перевірку зображення. Готові сцени збережені; повторно надішліть свої цілі, щоб продовжити, або почніть з /start з іншими фото 💛",
                                          "Один из сюжетов не прошёл проверку изображения. Готовые сцены сохранены; повторно отправьте свои цели, чтобы продолжить, или начните с /start с другими фото 💛",
                                          "One scene did not pass the image check. Finished scenes are saved; resend the same 5 to 9 goals to continue, or send /start with different photos 💛"))
        else:
            await state.update_data(blocked_input=True)
            await message.answer(text_for(lang,
                                          "Сервіс відхилив вхідне фото або формулювання. Ваші цілі й стиль збережено. Оберіть інше фото чи уточніть цілі 💛",
                                          "Сервис отклонил входное фото или формулировку. Ваши цели и стиль сохранены. Выберите другое фото или уточните цели 💛",
                                          "The service declined an input photo or wording. Your 5 to 9 goals and style are saved. Choose another photo or revise the goals 💛"),
                                 reply_markup=safety_recovery_keyboard(lang, len(photos)))
        return
    except Exception:
        logger.exception("Wallpaper rendering failed for user %s", message.from_user.id)
        await state.set_state(WallpaperStates.waiting_for_goals)
        await message.answer(text_for(lang,
                                      "Вибачте, не вдалося завершити візуалізацію. Фото й цілі збережено; повторно надішліть цілі трохи пізніше або /start, щоб почати заново.",
                                      "Простите, не удалось закончить визуализацию. Фото и цели сохранены; повторно отправьте цели немного позже или /start, чтобы начать заново.",
                                      "Sorry, I couldn't finish it. Your photos and goals are saved; resend the goals later to retry, or use /start to begin again.",
                                      ))
        return
    finally:
        try:
            await notice.delete()
        except Exception:
            logger.debug("Progress message could not be deleted for user %s", message.from_user.id)

    await message.answer_photo(FSInputFile(str(preview)), caption=text_for(
        lang, "Ваш подарунок готовий 💛 Можна зберегти заставку без напису PREVIEW.",
        "Ваш подарок готов 💛 Можно сохранить заставку без надписи PREVIEW.",
        "Your gift is ready 💛 You can save the artwork without the PREVIEW mark.",
    ))
    if free_access:
        order = None
        if session_factory is not None:
            async with session_factory() as session:
                repository = WallpaperOrderRepository(session)
                order = await repository.create(
                    telegram_user_id=message.from_user.id,
                    amount=Decimal("0"),
                    mobile_path=str(mobile),
                    desktop_path=str(desktop),
                    stars_amount=0,
                    goals=list(goals),
                    scene_prompts=list(job["scenes"]),
                    scene_assignments=list(job["assignments"]),
                    source_photo_paths=archived_sources,
                    visual_style=style,
                    raw_mobile_path=str(raw_mobile),
                    raw_desktop_path=str(raw_desktop),
                )
                await repository.mark_paid(order, f"VIP_JOB_{job['id']}", "vip_bypass")
        await _send_full(message, mobile, desktop, lang)
        await message.answer(
            text_for(
                lang,
                "🎬 Хочете оживити цей колаж? Створіть окрему відеоісторію у Scene Studio.",
                "🎬 Хотите оживить этот коллаж? Создайте отдельную видеоисторию в Scene Studio.",
                "🎬 Bring this collage to life with a separate video story in Scene Studio.",
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=text_for(lang, "🎬 Створити відеоісторію", "🎬 Создать видеоисторию",
                                  "🎬 Create video story"),
                    callback_data="gift_video_plans",
                )
            ]]),
        )
        if settings.portmone_test_mode:
            await send_portmone_sandbox_offer(
                bot=message.bot,
                settings=settings,
                session_factory=session_factory,
                telegram_user_id=message.from_user.id,
                product="wallpaper",
                reference_id=str(order.id if order else job["id"]),
                language=lang,
            )
        wayforpay = WayForPayService(settings)
        if wayforpay.ready:
            try:
                async with session_factory() as session:
                    attempt, checkout_url = await wayforpay.create_checkout(
                        session,
                        telegram_user_id=message.from_user.id,
                        product="wallpaper",
                        reference_id=str(order.id if order else job["id"]),
                        description=f"Food Porn digital gift #{job['id']}",
                        grants_entitlement=False,
                    )
                await message.answer(
                    text_for(
                        lang,
                        "🧪 Тестова оплата WayForPay для VIP. Подарунок вже відкритий.",
                        "🧪 Тестовая оплата WayForPay для VIP. Подарок уже открыт.",
                        "🧪 VIP WayForPay test. Your gift is already unlocked.",
                    ),
                    reply_markup=add_wayforpay_option(
                        None,
                        product="wallpaper",
                        reference_id=int(attempt.reference_id) if attempt.reference_id.isdigit() else attempt.id,
                        payment_id=attempt.id,
                        checkout_url=checkout_url,
                        amount=f"{attempt.amount:.2f}",
                        language=lang,
                        test_mode=attempt.test_mode,
                    ),
                )
            except Exception:
                logger.exception("Could not create VIP WayForPay gift checkout")
        await state.clear()
        await state.update_data(ui_lang=lang, lang_selected=selected)
        return

    try:
        ai_cost = ai_concept_cost + renderer.total_cost_usd
        price = checkout_price_uah(ai_cost, settings.usd_exchange_rate)
    except ValueError:
        logger.exception("Cannot determine actual API cost for gift")
        await message.answer("Не вдалося розрахувати вартість за фактичними токенами. Оплату не запитуємо.")
        await state.clear()
        await state.update_data(ui_lang=lang, lang_selected=selected)
        return
    async with session_factory() as session:
        order = await WallpaperOrderRepository(session).create(
            telegram_user_id=message.from_user.id, amount=price,
            mobile_path=str(mobile), desktop_path=str(desktop),
            stars_amount=settings.gift_price_stars,
            goals=list(goals),
            scene_prompts=list(job["scenes"]),
            scene_assignments=list(job["assignments"]),
            source_photo_paths=archived_sources,
            visual_style=style,
            raw_mobile_path=str(raw_mobile),
            raw_desktop_path=str(raw_desktop),
        )
    buttons = None
    if order.stars_amount:
        try:
            url = await create_invoice(message.bot, OrderRef(
                "wallpaper", order.id, message.from_user.id, order.stars_amount))
            buttons = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=text_for(lang, f"⭐ Отримати подарунок · {order.stars_amount} Stars",
                                                    f"⭐ Получить подарок · {order.stars_amount} Stars",
                                                    f"⭐ Get the gift · {order.stars_amount} Stars"), url=url)],
                [InlineKeyboardButton(text=text_for(lang, "🔄 Перевірити оплату", "🔄 Проверить оплату", "🔄 Check payment"),
                                      callback_data=f"check_pay_{order.id}")],
            ])
        except Exception:
            logger.exception("Could not create wallpaper Stars invoice %s", order.id)
    wayforpay = WayForPayService(settings)
    wayforpay_amount = None
    if wayforpay.ready:
        try:
            async with session_factory() as session:
                attempt, checkout_url = await wayforpay.create_checkout(
                    session,
                    telegram_user_id=message.from_user.id,
                    product="wallpaper",
                    reference_id=order.id,
                    description=f"Food Porn digital gift #{order.id}",
                )
            wayforpay_amount = attempt.amount
            buttons = add_wayforpay_option(
                buttons,
                product="wallpaper",
                reference_id=order.id,
                payment_id=attempt.id,
                checkout_url=checkout_url,
                amount=f"{attempt.amount:.2f}",
                language=lang,
                test_mode=attempt.test_mode,
            )
        except Exception:
            logger.exception("Could not create WayForPay gift checkout %s", order.id)
    if buttons is None:
        await message.answer("Оплата тимчасово недоступна. Колаж збережено; спробуйте пізніше.")
        return
    await message.answer(text_for(
        lang,
        f"Повний цифровий подарунок: {f'{wayforpay_amount:.2f} UAH' if wayforpay_amount is not None else f'{order.stars_amount} Stars'}. 💛",
        f"Полный цифровой подарок: {f'{wayforpay_amount:.2f} UAH' if wayforpay_amount is not None else f'{order.stars_amount} Stars'}. 💛",
        f"Complete digital gift: {f'{wayforpay_amount:.2f} UAH' if wayforpay_amount is not None else f'{order.stars_amount} Stars'}. 💛",
    ), reply_markup=buttons, parse_mode="HTML")
    await message.answer(
        text_for(
            lang,
            "🎬 Після підтвердження оплати ви зможете створити окрему відеоісторію.",
            "🎬 После подтверждения оплаты вы сможете создать отдельную видеоисторию.",
            "🎬 After payment confirmation, you can create a separate video story.",
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=text_for(lang, "🎬 Відеоісторія", "🎬 Видеоистория", "🎬 Video story"),
                callback_data="gift_video_plans",
            )
        ]]),
    )
    await state.clear()
    await state.update_data(ui_lang=lang, lang_selected=selected)


@router.callback_query(F.data.startswith("check_pay_"))
async def verify_wallpaper_payment(callback: CallbackQuery, settings: Settings,
                                   session_factory: async_sessionmaker[AsyncSession],
                                   state: FSMContext) -> None:
    lang = (await state.get_data()).get("ui_lang") or language_for(callback.from_user)
    try:
        order_id = int((callback.data or "").removeprefix("check_pay_"))
    except ValueError:
        await callback.answer("Некоректний номер замовлення.", show_alert=True)
        return
    async with session_factory() as session:
        repo = WallpaperOrderRepository(session)
        order = await repo.get_for_user(order_id, callback.from_user.id)
        if order is None:
            await callback.answer("Замовлення не знайдено.", show_alert=True)
            return
        if not order.paid:
            if getattr(order, "stars_amount", None):
                await callback.answer("Оплата Stars ещё обрабатывается Telegram.", show_alert=True)
                return
            try:
                verified = await PaymentService(settings).verify_portmone_payment(
                    order_id, order.amount, product="wallpaper",
                )
            except Exception:
                logger.exception("Wallpaper payment verification failed for order %s", order_id)
                await callback.answer("Не вдалося перевірити оплату. Спробуйте пізніше.", show_alert=True)
                return
            if verified is None:
                await callback.answer(text_for(lang, "Оплату ще не підтверджено Portmone.",
                                               "Оплата пока не подтверждена Portmone.",
                                               "Portmone has not confirmed the payment yet."), show_alert=True)
                return
        mobile, desktop = Path(order.mobile_path), Path(order.desktop_path)
        if not mobile.is_file() or not desktop.is_file():
            await callback.answer("Платіж отримано, але файли недоступні. Напишіть в підтримку.", show_alert=True)
            return
        if not order.paid:
            await repo.mark_paid(order, verified.payment_id)
        await callback.answer(text_for(lang, "Оплату підтверджено!",
                                       "Оплата подтверждена!", "Payment confirmed!"))
        await _send_full(callback.message, mobile, desktop, lang)
        try:
            archive = await asyncio.to_thread(
                create_print_bundle, order.id, mobile, desktop,
                width_mm=settings.print_poster_width_mm,
                height_mm=settings.print_poster_height_mm,
                dpi=settings.print_dpi,
            )
            await callback.message.answer_document(FSInputFile(str(archive)), caption=text_for(lang,
                                                                                               "Архів для друкарні 💛 Усередині постер, PDF, оригінали й параметри друку. "
                                                                                               "Перед великим тиражем попросіть пробний друк.",
                                                                                               "Архив для типографии 💛 Внутри постер, PDF, оригиналы и параметры печати. "
                                                                                               "Перед большим тиражом попросите пробную печать.",
                                                                                               "Print archive 💛 Contains the poster, PDF, originals and print details. "
                                                                                               "Please request a proof before a large run."))
        except Exception:
            logger.exception("Could not deliver print bundle for paid order %s", order.id)
            await callback.message.answer(text_for(lang,
                                                   "Оплату підтверджено, зображення надіслано. Архів ще не готовий; повторіть перевірку пізніше.",
                                                   "Оплата подтверждена, изображения отправлены. Архив ещё не готов; повторите проверку позже.",
                                                   "Payment confirmed and images sent. The print archive is not ready; check again later."))


@router.callback_query(F.data == "order_print_poster")
async def process_print_order(callback: CallbackQuery) -> None:
    await callback.answer("Друк постерів поки недоступний.", show_alert=True)
