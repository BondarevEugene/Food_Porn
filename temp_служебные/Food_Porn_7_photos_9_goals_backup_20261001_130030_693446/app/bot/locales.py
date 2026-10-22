"""
==========================================================
FOOD_PORN & OLD MONEY MANIFESTATIONS
Module: Localization Strings (UK / EN)
==========================================================
"""

STRINGS = {
    "uk": {
        "intro": (
            "🎁 <b>Подарунок для близької людини</b>\n\n"
            "Надішліть одне або п’ять фото та напишіть свої 5 цілей. "
            "Я сам підберу до кожної цілі фото, фон і сюжет."
        ),
        "btn_generate": "✨ Втілити в реальність",
        "missing_goals": "🖋 Надішліть саме 5 цілей, кожну з нового рядка.",
        "generating": "🕰 <i>Створюємо ваш колаж із фотографій... 🍷</i>",
        "vip_success": "⚜️ <b>Ваша реальність (VIP-доступ) успішно створена.</b>",
        "preview_caption": "💛 <i>Ваш подарунок готовий</i>",
        "concept_ready": (
            "⚜️ <b>Концепт успішно створено.</b>\n\n"
            "Для розблокування повного пакету (мобільна заставка, десктопні шпалери та доступ до друку) активуйте доступ."
        ),
        "btn_pay": "💳 Оплатити {price} {currency} через Portmone",
        "btn_check_pay": "🔄 Перевірити статус оплати",
        "mobile_caption": "📱 <i>Ексклюзивна заставка на мобільний (9:16)</i>",
        "desktop_caption": "💻 <i>Шпалери на робочий стіл ПК (16:9)</i>",
        "print_offer": (
            "📦 <b>Бажаєте перенести вашу маніфестацію у реальний світ?</b>\n\n"
            "Ми можемо надрукувати преміальний постер у розмірі 300x400 мм (300 DPI) на щільному арт-папері."
        ),
        "btn_print": "📦 Замовити друкований постер (300x400 мм)",
        "print_success": (
            "📦 <b>Замовлення на друкований постер успішно сформовано!</b>\n\n"
            "Партнер-типографія отримала специфікацію 300x400 мм (300 DPI) і зв'яжеться з вами для уточнення деталей."
        ),
    },
    "en": {
        "intro": (
            "🎁 <b>A gift for someone special</b>\n\n"
            "Send one or five photos and write your 5 goals. "
            "I'll match each goal with a photo, background and scene."
        ),
        "btn_generate": "✨ Manifest Reality",
        "missing_goals": "🖋 Send exactly 5 goals, one per line.",
        "generating": "🕰 <i>Creating your collage from the photographs... 🍷</i>",
        "vip_success": "⚜️ <b>Your reality (VIP Access) has been successfully created.</b>",
        "preview_caption": "💛 <i>Your gift is ready</i>",
        "concept_ready": (
            "⚜️ <b>Concept successfully created.</b>\n\n"
            "To unlock the full package (mobile wallpaper, desktop background, and print access), activate your pass."
        ),
        "btn_pay": "💳 Pay {price} {currency} via Portmone",
        "btn_check_pay": "🔄 Check Payment Status",
        "mobile_caption": "📱 <i>Exclusive Mobile Wallpaper (9:16)</i>",
        "desktop_caption": "💻 <i>Desktop Wallpaper (16:9)</i>",
        "print_offer": (
            "📦 <b>Would you like to bring your manifestation into the physical world?</b>\n\n"
            "We can print a premium poster sized 300x400 mm (300 DPI) on heavy art paper."
        ),
        "btn_print": "📦 Order Printed Poster (300x400 mm)",
        "print_success": (
            "📦 <b>Printed poster order successfully placed!</b>\n\n"
            "Our print partner has received the 300x400 mm (300 DPI) specs and will contact you for delivery details."
        ),
    }
}


def get_text(lang: str, key: str, **kwargs) -> str:
    lang_dict = STRINGS.get(lang, STRINGS["uk"])
    text = lang_dict.get(key, STRINGS["uk"].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text
