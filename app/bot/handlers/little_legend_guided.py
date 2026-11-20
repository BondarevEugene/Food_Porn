"""Private-chat guided story intake. Drafts never trigger paid AI work."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.little_legend.router import StoryDraft, create_story
from app.little_legend.story_modes import (
    ClassicSource,
    SimpleBrief,
    StoryEntry,
    StoryMode,
    brief_outline,
    brief_parent_sketch,
)

router = Router(name="little_legend_guided")


class BookIntake(StatesGroup):
    hero = State()
    characters = State()
    events = State()
    moral = State()
    classic_title = State()
    classic_original_hero = State()
    photo_consent = State()
    photos = State()
    confirm = State()


def _buttons(*pairs: tuple[str, str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=data)]
        for label, data in pairs
    ])


async def _private(message: Message) -> bool:
    if message.chat.type != "private" or message.from_user is None:
        await message.answer("Создание детской книги доступно только в личном чате.")
        return False
    return True


@router.callback_query(F.data.in_({"ll_mode:brief", "ll_mode:classic"}))
async def start_guided(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or not await _private(callback.message):
        await callback.answer()
        return
    mode = (callback.data or "").split(":")[-1]
    await state.clear()
    await state.update_data(mode=mode)
    await state.set_state(BookIntake.hero)
    await callback.message.answer(
        "📖 Шаг 2/5 · Как зовут ребёнка — главного героя?\n"
        "Напишите имя одним сообщением.",
        reply_markup=_buttons(("✖️ Отменить", "ll_intake_cancel")),
    )
    await callback.answer()


@router.message(BookIntake.hero, F.text)
async def receive_hero(message: Message, state: FSMContext) -> None:
    if not await _private(message):
        return
    name = message.text.strip()
    if not 1 <= len(name) <= 100:
        await message.answer("Укажите имя длиной до 100 символов.")
        return
    await state.update_data(hero=name)
    data = await state.get_data()
    if data["mode"] == StoryMode.BRIEF:
        await state.set_state(BookIntake.characters)
        await message.answer("📖 Шаг 3/5 · Кто ещё участвует? Перечислите через запятую.")
    else:
        await state.set_state(BookIntake.classic_title)
        await message.answer("📖 Шаг 3/5 · Название классической сказки?")


@router.message(BookIntake.characters, F.text)
async def receive_characters(message: Message, state: FSMContext) -> None:
    if not await _private(message):
        return
    names = [part.strip() for part in message.text.split(",") if part.strip()]
    if not 1 <= len(names) <= 20 or any(len(x) > 100 for x in names):
        await message.answer("Укажите от 1 до 20 персонажей, разделённых запятыми.")
        return
    await state.update_data(characters=names)
    await state.set_state(BookIntake.events)
    await message.answer(
        "📖 Шаг 4/5 · Что должно произойти? "
        "Перечислите 1–12 событий, каждое с новой строки."
    )


@router.message(BookIntake.events, F.text)
async def receive_events(message: Message, state: FSMContext) -> None:
    if not await _private(message):
        return
    events = [part.strip() for part in message.text.splitlines() if part.strip()]
    if not 1 <= len(events) <= 12 or any(len(x) > 1000 for x in events):
        await message.answer("Напишите от 1 до 12 событий, каждое до 1000 символов.")
        return
    await state.update_data(events=events)
    await state.set_state(BookIntake.moral)
    await message.answer(
        "📖 Шаг 5/5 · Какую мысль должна передать сказка? "
        "Напишите мораль или нажмите «Пропустить».",
        reply_markup=_buttons(("Пропустить", "ll_intake_skip_moral")),
    )


@router.callback_query(BookIntake.moral, F.data == "ll_intake_skip_moral")
async def skip_moral(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(moral="")
    await _request_photo_consent(callback.message, state)
    await callback.answer()


@router.message(BookIntake.moral, F.text)
async def receive_moral(message: Message, state: FSMContext) -> None:
    if not await _private(message):
        return
    if len(message.text) > 1000:
        await message.answer("Сократите мораль до 1000 символов.")
        return
    await state.update_data(moral=message.text.strip())
    await _request_photo_consent(message, state)


@router.message(BookIntake.classic_title, F.text)
async def receive_classic_title(message: Message, state: FSMContext) -> None:
    if not await _private(message):
        return
    title = message.text.strip()
    if not 2 <= len(title) <= 180:
        await message.answer("Название должно содержать от 2 до 180 символов.")
        return
    await state.update_data(classic_title=title)
    await state.set_state(BookIntake.classic_original_hero)
    await message.answer("📖 Шаг 4/5 · Как зовут оригинального героя сказки?")


@router.message(BookIntake.classic_original_hero, F.text)
async def receive_original_hero(message: Message, state: FSMContext) -> None:
    if not await _private(message):
        return
    original = message.text.strip()
    if not 1 <= len(original) <= 100:
        await message.answer("Укажите имя персонажа до 100 символов.")
        return
    await state.update_data(original_hero=original)
    await _request_photo_consent(message, state)


async def _request_photo_consent(message: Message, state: FSMContext) -> None:
    await state.set_state(BookIntake.photo_consent)
    await message.answer(
        "📷 Фото ребёнка необязательно. Если хотите добавить фото, "
        "подтвердите, что вы родитель или законный представитель и "
        "разрешаете использовать изображение для создания книги. "
        "Фото пока сохраняется только как Telegram file_id, "
        "без скачивания и без запуска AI.",
        reply_markup=_buttons(
            ("✅ Разрешаю использовать фото", "ll_photo_consent_yes"),
            ("Пропустить фото", "ll_photo_skip"),
            ("✖️ Отменить", "ll_intake_cancel"),
        ),
    )


@router.callback_query(BookIntake.photo_consent, F.data == "ll_photo_consent_yes")
async def allow_photos(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(photo_consent_confirmed=True, photo_reference_ids=[])
    await state.set_state(BookIntake.photos)
    await callback.message.answer(
        "📷 Отправьте до 5 фотографий отдельными сообщениями. "
        "Когда закончите, нажмите «Готово».",
        reply_markup=_buttons(
            ("✅ Готово", "ll_photo_done"),
            ("✖️ Отменить", "ll_intake_cancel"),
        ),
    )
    await callback.answer()


@router.message(BookIntake.photos, F.photo)
async def collect_photo(message: Message, state: FSMContext) -> None:
    if not await _private(message):
        return
    data = await state.get_data()
    references = data.get("photo_reference_ids", [])
    if len(references) >= 5:
        await message.answer("Максимум 5 фотографий. Нажмите «Готово».")
        return
    file_id = message.photo[-1].file_id
    if file_id not in references:
        references.append(file_id)
        await state.update_data(photo_reference_ids=references)
    await message.answer(
        f"📷 Добавлено {len(references)}/5.",
        reply_markup=_buttons(("✅ Готово", "ll_photo_done")),
    )


@router.callback_query(BookIntake.photos, F.data == "ll_photo_done")
async def finish_photos(callback: CallbackQuery, state: FSMContext) -> None:
    await _review(callback.message, state)
    await callback.answer()


@router.callback_query(BookIntake.photo_consent, F.data == "ll_photo_skip")
async def skip_photos(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(photo_consent_confirmed=False, photo_reference_ids=[])
    await _review(callback.message, state)
    await callback.answer()


async def _review(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(BookIntake.confirm)
    if data["mode"] == StoryMode.BRIEF:
        description = (
            f"✨ Герой: {data['hero']}\n"
            f"Персонажи: {', '.join(data['characters'])}\n"
            f"События: {len(data['events'])}\n"
            f"Мораль: {data.get('moral') or 'на усмотрение автора'}"
        )
    else:
        description = (
            f"🏰 Герой: {data['hero']}\n"
            f"Сказка: {data['classic_title']}\n"
            f"Заменяем персонажа: {data['original_hero']}\n"
            "⚠️ Права на конкретную версию ещё не проверены. "
            "Генерация заблокирована до проверки."
        )
    await message.answer(
        "📖 Проверьте замысел:\n\n" + description
        + "\n\nСохранить черновик? Это бесплатно, генерация не запускается.",
        reply_markup=_buttons(
            ("💾 Сохранить черновик", "ll_intake_save"),
            ("✖️ Отменить", "ll_intake_cancel"),
        ),
    )


@router.callback_query(F.data == "ll_intake_cancel")
async def cancel_intake(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer(
        "Создание отменено. Выберите сценарий снова.",
        reply_markup=_buttons(("⬅️ К сценариям", "ll_choose_mode")),
    )
    await callback.answer()


@router.callback_query(BookIntake.confirm, F.data == "ll_intake_save")
async def save_intake(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or not await _private(callback.message):
        await callback.answer()
        return
    data = await state.get_data()
    if data.get("saving"):
        await callback.answer("Сохранение уже выполняется")
        return
    await state.update_data(saving=True)
    hero = data["hero"]
    if data["mode"] == StoryMode.BRIEF:
        brief = SimpleBrief(
            child_hero=hero,
            characters=data["characters"],
            events=data["events"],
            moral=data.get("moral", ""),
        )
        outline = brief_outline(brief, chapter_count=max(3, len(brief.events)))
        draft = StoryDraft(
            title=f"Сказка про {hero}",
            hero=hero,
            entry=StoryEntry(
                mode=StoryMode.BRIEF, brief=brief,
                photo_reference_ids=data.get("photo_reference_ids", []),
                photo_consent_confirmed=data.get("photo_consent_confirmed", False),
            ),
            parent_sketch=brief_parent_sketch(brief),
            graph=outline.graph,
            design=outline.design,
            setup="; ".join(brief.events),
        )
    else:
        source = ClassicSource(
            title=data["classic_title"],
            original_hero=data["original_hero"],
            child_hero=hero,
        )
        draft = StoryDraft(
            title=f"{source.title} — {hero}",
            hero=hero,
            entry=StoryEntry(
                mode=StoryMode.CLASSIC, classic=source,
                photo_reference_ids=data.get("photo_reference_ids", []),
                photo_consent_confirmed=data.get("photo_consent_confirmed", False),
            ),
            setup=f"Адаптация: {source.title}; оригинальный герой: {source.original_hero}",
        )
    try:
        result = await create_story(draft, owner=callback.from_user.id)
    except Exception:
        await state.update_data(saving=False)
        await callback.message.answer(
            "⚠️ Не удалось сохранить черновик. Попробуйте ещё раз позже."
        )
        await callback.answer()
        return
    await state.clear()
    await callback.message.answer(
        f"✅ Черновик #{result['id']} сохранён.\n"
        "Перед генерацией нужно утвердить план и проверить необходимые согласия.",
        reply_markup=_buttons(
            ("📚 Мои книги", "ll_books"),
            ("✨ Создать ещё", "ll_choose_mode"),
        ),
    )
    await callback.answer()
