"""
==========================================================
FOOD_PORN

Module: Premium AI Manifestation Handlers
Layer: Telegram Interface (Old Money Aesthetic)
==========================================================
"""

import os
import shutil
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, FSInputFile, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from dotenv import load_dotenv
from PIL import Image, ImageOps

from app.bot.states.wallpaper import WallpaperStates

router = Router(name="wallpaper")

VIP_USERS = ["Voloshka0602", "MenuDishesForLove", "bondarev_e"]

def is_vip(user) -> bool:
    return user.username in VIP_USERS if user.username else False

def get_payment_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Активувати Premium", url="https://portmone.com/")],
            [InlineKeyboardButton(text="🔄 Перевірити статус", callback_data=f"check_wp_pay_{order_id}")],
        ]
    )

def generate_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✨ Втілити в реальність")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

@router.callback_query(F.data == "start_wallpaper_flow")
async def start_wallpaper(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()

    upload_dir = Path("storage/uploads/wallpapers") / str(callback.from_user.id)
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)

    await state.set_state(WallpaperStates.waiting_for_photos)

    text = (
        "🗝 <b>Закритий Генератор Маніфестацій</b>\n\n"
        "Забудьте про шаблонні картинки з інтернету. Штучний інтелект візьме "
        "<b>саме ваші завантажені фотографії</b> та переосмислить їх у безшовний шедевр Old Money.\n\n"
        "🍷 <b>Що потрібно від вас:</b>\n"
        "1. Надішліть ваші найкращі <b>фото</b> (обличчя, стиль, атмосфера).\n"
        "2. Напишіть ваші <b>цілі</b> (кожна з нового рядка).\n\n"
        "<i>Коли завершите — натисніть кнопку внизу.</i>"
    )

    if callback.message:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="HTML", reply_markup=generate_keyboard())
    await callback.answer()


@router.message(WallpaperStates.waiting_for_photos, F.photo | F.document)
async def collect_photo(message: Message) -> None:
    if message.document and not message.document.mime_type.startswith("image/"):
        return

    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    file = await message.bot.get_file(file_id)

    upload_dir = Path("storage/uploads/wallpapers") / str(message.from_user.id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / f"{message.message_id}.jpg"
    await message.bot.download_file(file.file_path, destination=file_path)


@router.message(WallpaperStates.waiting_for_photos, F.text & ~F.text.in_({"✨ Втілити в реальність"}))
async def collect_goals(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    goals = data.get("goals", [])
    new_goals = [line.strip() for line in message.text.split("\n") if line.strip()]
    goals.extend(new_goals)
    await state.update_data(goals=goals)


def prepare_user_source_image(user_id: int) -> Path | None:
    """Собирает все загруженные пользователем фотографии (до 5 шт.) в единый художественный мудборд-колаж."""
    upload_dir = Path("storage/uploads/wallpapers") / str(user_id)
    if not upload_dir.exists():
        return None

    image_paths = sorted(list(upload_dir.glob("*.jpg")) + list(upload_dir.glob("*.png")))
    if not image_paths:
        return None

    processed_path = upload_dir / "prepared_source.png"

    try:
        images = []
        for p in image_paths[:5]:  # Берем все 5 фото
            img = Image.open(p).convert("RGBA")
            images.append(img)

        if not images:
            return None

        canvas = Image.new("RGBA", (1024, 1024), (20, 18, 22, 255))
        num_photos = len(images)
        padding = 12

        if num_photos == 5:
            w1 = (1024 - padding * 4) // 3
            h1 = 480
            for i in range(3):
                if i < len(images):
                    im_fit = ImageOps.fit(images[i], (w1, h1), method=Image.Resampling.LANCZOS)
                    x = padding + i * (w1 + padding)
                    y = padding
                    canvas.paste(im_fit, (x, y))

            w2 = (1024 - padding * 3) // 2
            h2 = 500
            for i in range(2):
                idx = 3 + i
                if idx < len(images):
                    im_fit = ImageOps.fit(images[idx], (w2, h2), method=Image.Resampling.LANCZOS)
                    x = padding + i * (w2 + padding)
                    y = padding + h1 + padding
                    canvas.paste(im_fit, (x, y))
        else:
            w_box = (1024 - padding * 3) // 2
            h_box = (1024 - padding * 3) // 2
            for i, img in enumerate(images[:4]):
                r = i // 2
                c = i % 2
                im_fit = ImageOps.fit(img, (w_box, h_box), method=Image.Resampling.LANCZOS)
                x = padding + c * (w_box + padding)
                y = padding + r * (h_box + padding)
                canvas.paste(im_fit, (x, y))

        canvas.save(processed_path, "PNG")
        return processed_path
    except Exception:
        return None


@router.message(WallpaperStates.waiting_for_photos, F.text == "✨ Втілити в реальність")
async def generate_wallpapers(message: Message, state: FSMContext) -> None:
    from app.services.wallpaper_renderer import (
        WallpaperRenderer,
        WallpaperBillingError,
        WallpaperRateLimitError
    )

    data = await state.get_data()
    goals = data.get("goals", [])

    if not goals:
        await message.answer("🖋 Ви забули вказати свої цілі. Напишіть хоча б кілька рядків.")
        return

    wait_msg = await message.answer(
        "🕰 <i>Штучний інтелект створює ваш персональний арт-колаж з усіх завантажених фото та цілей... 🍷</i>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1.5")
    image_size = os.getenv("OPENAI_IMAGE_SIZE", "1024x1024")

    if not api_key:
        await wait_msg.delete()
        await message.answer("⚠️ Помилка доступу: Ключ OpenAI не знайдено.")
        return

    upload_dir = Path("storage/uploads/wallpapers") / str(message.from_user.id)
    photo_count = len(list(upload_dir.glob("*.jpg"))) + len(list(upload_dir.glob("*.png"))) if upload_dir.exists() else 1

    renderer = WallpaperRenderer(
        api_key=api_key,
        model=model_name,
        output_dir=Path(f"storage/wallpapers/{message.from_user.id}")
    )

    goals_str = ", ".join(goals[:5])

    prompt = (
        f"A breathtaking, hyper-realistic luxury fine art multi-image collage and wallpaper in strict Old Money aesthetic. "
        f"Incorporate elements, atmosphere, and visual motifs from all {photo_count} user-uploaded reference photos. "
        f"Deep graphite, warm dark brown, and soft gold tones, cinematic Vogue editorial lighting. "
        f"Harmoniously integrate visual representations of these exact personal goals: {goals_str}. "
        f"Seamless composition, masterpiece. NO random external people, ONLY authentic elements from the user's references."
    )

    try:
        result = await renderer.generate_image(
            prompt=prompt,
            size=image_size,
            file_name=f"manifestation_{message.from_user.id}.png"
        )

    except WallpaperBillingError:
        await wait_msg.delete()
        await message.answer("⚠️ Помилка: вичерпано баланс OpenAI.")
        return
    except WallpaperRateLimitError:
        await wait_msg.delete()
        await message.answer("⚠️ Сервери перевантажені. Спробуйте за хвилину.")
        return
    except Exception as e:
        await wait_msg.delete()
        await message.answer(f"⚠️ Помилка генерації: {e}")
        return

    await wait_msg.delete()

    user_is_vip = is_vip(message.from_user)

    if user_is_vip:
        await message.answer("⚜️ <b>Ваша реальність на основі всіх фото та цілей успішно створена.</b>", parse_mode="HTML")
        await message.answer_document(
            FSInputFile(str(result.path)),
            caption="🖼 <i>Original HQ Fine Art (Print Quality)</i>",
            parse_mode="HTML"
        )
        await message.answer_photo(
            FSInputFile(str(result.path)),
            caption="📱 <i>Mobile Aesthetic Wallpaper (9:16)</i>",
            parse_mode="HTML"
        )
        await state.clear()
    else:
        await message.answer_photo(FSInputFile(str(result.path)), caption="📱 <i>Прев'ю маніфестації</i>", parse_mode="HTML")
        await message.answer(
            "⚜️ <b>Концепт створено.</b>\n\n"
            "Щоб отримати оригінал у максимальній роздільній здатності, активуйте преміум-доступ.",
            reply_markup=get_payment_keyboard(order_id=message.from_user.id),
            parse_mode="HTML"
        )
