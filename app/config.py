"""
==========================================================
FOOD_PORN & OLD MONEY MANIFESTATIONS

Module: Runtime Configuration
Layer: Application Core
==========================================================
"""

from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    # Telegram & Database
    bot_token: str = "replace_me"
    database_url: str = "postgresql+asyncpg://USER:PASSWORD@localhost/DATABASE"

    # APIs
    openai_api_key: SecretStr = SecretStr("replace_me")
    # Organization Admin key is separate from the normal project API key and
    # is used only to import actual billed costs into the CRM.
    openai_admin_api_key: SecretStr = SecretStr("")
    openai_project_id: str = ""
    spoonacular_api_key: SecretStr = SecretStr("replace_me")

    # Generation Toggles
    use_mock_images: bool = Field(default=False)

    # OpenAI Settings
    openai_image_model: str = "gpt-image-1.5"
    openai_image_size: str = "1024x1024"
    openai_image_quality: str = "medium"
    wallpaper_image_model: str = "gpt-image-2.5-sunburst"
    wallpaper_image_quality: str = "xhigh"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"
    gift_video_seconds: int = Field(default=15, ge=10, le=20)
    recipe_model: str = "gpt-4o-mini"
    openai_text_input_usd_per_million: Decimal = Field(default=Decimal("0.15"), ge=0)
    openai_text_output_usd_per_million: Decimal = Field(default=Decimal("0.60"), ge=0)
    openai_cached_input_usd_per_million: Decimal = Field(default=Decimal("0.075"), ge=0)
    openai_image_fallback_cost_usd: Decimal = Field(default=Decimal("0.040"), ge=0)
    openai_tts_fallback_cost_usd: Decimal = Field(default=Decimal("0.020"), ge=0)
    openai_cost_sync_enabled: bool = False
    openai_cost_sync_interval_minutes: int = Field(default=60, ge=15, le=1440)
    openai_cost_sync_days: int = Field(default=35, ge=1, le=180)

    # Application Configuration
    app_env: str = "development"
    log_level: str = "INFO"
    storage_root: Path = Path("storage")
    # Public HTTPS address of the Telegram Mini App. Leave empty until deployed.
    miniapp_url: str = ""
    channel_link_secret: SecretStr = SecretStr("")
    channel_link_ttl_hours: int = Field(default=168, ge=1, le=720)
    miniapp_port: int = Field(default=8080, ge=1, le=65535)
    max_upload_mb: int = Field(default=20, ge=1, le=50)
    image_concurrency: int = Field(default=1, ge=1, le=3)
    image_retries: int = Field(default=2, ge=1, le=4)
    openai_quota_cooldown_seconds: int = Field(default=300, ge=30, le=3600)
    enable_image_cache: bool = True

    # Omnichannel messaging. Empty credentials keep an adapter disabled.
    meta_verify_token: SecretStr = SecretStr("")
    meta_app_secret: SecretStr = SecretStr("")
    meta_graph_api_version: str = "v24.0"
    whatsapp_access_token: SecretStr = SecretStr("")
    whatsapp_phone_number_id: str = ""
    messenger_page_access_token: SecretStr = SecretStr("")
    messenger_page_id: str = ""
    instagram_access_token: SecretStr = SecretStr("")
    instagram_business_account_id: str = ""
    viber_auth_token: SecretStr = SecretStr("")
    viber_bot_name: str = "Food Porn"
    slack_signing_secret: SecretStr = SecretStr("")
    slack_bot_token: SecretStr = SecretStr("")
    discord_public_key: str = ""

    # --- Комерційні параметри ---
    usd_exchange_rate: float = Field(default=41.5)

    price_electronic_uah: int = Field(default=500)
    price_print_uah: int = Field(default=1200)

    price_electronic_usd: int = Field(default=15)
    price_print_usd: int = Field(default=35)
    menu_price: float = Field(default=500.0, gt=0)
    currency: str = "UAH"
    menu_price_stars: int = Field(default=0, ge=0, le=100000)
    gift_price_stars: int = Field(default=0, ge=0, le=100000)
    # Opt-in only after end-to-end payment and persistent storage verification.
    gift_unified_checkout_enabled: bool = False
    video_story_price_stars: int = Field(default=0, ge=0, le=100000)
    video_economy_price_uah: Decimal = Field(default=Decimal("199.00"), gt=0, le=100000)
    video_cinematic_price_uah: Decimal = Field(default=Decimal("499.00"), gt=0, le=100000)
    video_premium_price_uah: Decimal = Field(default=Decimal("999.00"), gt=0, le=100000)

    # Портмоне платіжний шлюз
    portmone_gateway_url: str = Field(default="https://docs.portmone.com.ua/docs/uk/PaymentGatewayUa/")
    portmone_payee_id: str = Field(default="replace_me")
    portmone_login: str = Field(default="replace_me")
    portmone_password: SecretStr = SecretStr("replace_me")
    # Diagnostic card checkout. It must remain disabled outside Portmone sandbox.
    portmone_test_mode: bool = False
    portmone_test_amount_uah: Decimal = Field(default=Decimal("1.00"), gt=0, le=100)

    # Monobank Acquiring. MONO_TOKEN is issued in the merchant cabinet.
    mono_token: SecretStr = SecretStr("")
    mono_redirect_url: str = ""
    mono_webhook_url: str = ""

    # WayForPay hosted card checkout. In sandbox mode the application may use
    # the public test merchant from the official WayForPay documentation.
    public_base_url: str = ""
    wayforpay_merchant_account: str = ""
    wayforpay_merchant_secret_key: SecretStr = SecretStr("")
    wayforpay_merchant_domain: str = ""
    wayforpay_test_mode: bool = False
    wayforpay_menu_price_uah: Decimal = Field(default=Decimal("5.00"), gt=0, le=100000)
    wayforpay_wallpaper_price_uah: Decimal = Field(default=Decimal("1.00"), gt=0, le=100000)
    # Відео не продаємо, доки власник явно не встановить ціну.
    wayforpay_video_story_price_uah: Decimal | None = Field(default=None, gt=0, le=100000)

    # --- Настройки типографии ---
    printshop_email: str = ""
    printshop_name: str = Field(default="Студия Печати 'ArtPress'")
    print_poster_width_mm: int = Field(default=300)
    print_poster_height_mm: int = Field(default=400)
    print_dpi: int = Field(default=300)
    smtp_host: str = ""
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_use_tls: bool = True

    printshop_email_template: str = Field(
        default=(
            "Нове замовлення на друк постера (Old Money Manifestation)!\n\n"
            "Дані клієнта:\n"
            "• Telegram User ID: {user_id}\n"
            "• Username: @{username}\n"
            "• Телефон: {phone}\n"
            "• Місто/Країна: {city}, {country}\n\n"
            "Деталі замовлення:\n"
            "• Формат: Постер {width}x{height} мм ({dpi} DPI)\n"
            "• Шлях до файлу для друку: {file_path}\n"
        )
    )

    admin_telegram_ids: Annotated[tuple[int, ...], NoDecode] = ()
    crm_vip_telegram_ids: Annotated[tuple[int, ...], NoDecode] = ()
    free_generation_telegram_ids: Annotated[tuple[int, ...], NoDecode] = ()
    default_vip_users: list[str] = Field(default_factory=lambda: ["Voloshka0602", "MenuDishesForLove", "bondarev_e"])
    admin_username: str = ""
    admin_password: SecretStr = SecretStr("")
    admin_session_secret: SecretStr = SecretStr("")
    crm_encryption_key: SecretStr = SecretStr("")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            value = value.replace("postgres://", "postgresql+asyncpg://", 1)
        elif value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)

        url = make_url(value)
        if url.drivername != "postgresql+asyncpg":
            return value

        # Neon показывает URL для libpq/psycopg. Драйвер asyncpg принимает
        # параметр ``ssl``, но не понимает ``sslmode`` и ``channel_binding``.
        query = dict(url.query)
        ssl_mode = query.pop("sslmode", None)
        query.pop("channel_binding", None)
        if ssl_mode and "ssl" not in query:
            query["ssl"] = ssl_mode
        return url.set(query=query).render_as_string(hide_password=False)

    @field_validator("admin_telegram_ids", "crm_vip_telegram_ids", "free_generation_telegram_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> tuple[int, ...]:
        if value in (None, "", (), []):
            return ()
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return ()
            if normalized.startswith("["):
                decoded = json.loads(normalized)
                if not isinstance(decoded, list):
                    raise ValueError("ADMIN_TELEGRAM_IDS JSON value must be a list")
                return tuple(int(item) for item in decoded)
            return tuple(int(part.strip()) for part in normalized.split(",") if part.strip())
        return tuple(value)

    @property
    def uploads_dir(self) -> Path:
        return self.storage_root / "uploads"

    @property
    def generated_dir(self) -> Path:
        return self.storage_root / "generated"

    @property
    def cache_dir(self) -> Path:
        return self.storage_root / "cache"

    @property
    def demo_dir(self) -> Path:
        return self.storage_root / "demo"

    def ensure_directories(self) -> None:
        for path in (self.uploads_dir, self.generated_dir, self.cache_dir, self.demo_dir):
            path.mkdir(parents=True, exist_ok=True)

    def validate_runtime(self) -> None:
        missing = []
        if not self.bot_token or self.bot_token == "replace_me":
            missing.append("BOT_TOKEN")
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# --- Гарантований експорт констант на рівні модуля для всіх імпортів ---
USD_EXCHANGE_RATE = 41.5
PRICE_ELECTRONIC_UAH = 500
PRICE_PRINT_UAH = 1200
PRICE_ELECTRONIC_USD = 15
PRICE_PRINT_USD = 35
PORTMONE_GATEWAY_URL = "https://docs.portmone.com.ua/docs/uk/PaymentGatewayUa/"
PRINT_SHOP_EMAIL = "bondarev.e.1707@gmail.com"
PRINT_SHOP_EMAIL_TEMPLATE = (
    "Нове замовлення на друк постера (Old Money Manifestation)!\n\n"
    "Дані клієнта:\n"
    "• Telegram User ID: {user_id}\n"
    "• Username: @{username}\n"
    "• Телефон: {phone}\n"
    "• Місто/Країна: {city}, {country}\n\n"
    "Деталі замовлення:\n"
    "• Формат: Постер {width}x{height} мм ({dpi} DPI)\n"
    "• Шлях до файлу для друку: {file_path}\n"
)
PRINT_POSTER_WIDTH_MM = 300
PRINT_POSTER_HEIGHT_MM = 400
PRINT_DPI = 300



# ==========================================================
# FOOD_PORN & OLD MONEY MANIFESTATIONS
# СПРАВОЧНИК ПАРАМЕТРОВ КОНФИГУРАЦИИ
# ==========================================================
#
# Назначение:
# Документация параметров класса Settings.
#
# ВАЖНО:
# 1. Параметры Settings загружаются из переменных окружения
#    и файла .env.
# 2. Имена переменных окружения соответствуют именам полей
#    без учёта регистра: bot_token = BOT_TOKEN.
# 3. SecretStr скрывает значение секрета при обычном выводе.
# 4. После изменения .env необходимо перезапустить приложение.
# 5. Не публикуйте токены, пароли и ключи шифрования.
#
# ==========================================================
# 1. TELEGRAM И БАЗА ДАННЫХ
# ==========================================================
#
# bot_token: str
# Токен Telegram-бота, полученный от @BotFather.
# Необходим для подключения бота к Telegram API.
# Обязателен для запуска: validate_runtime() проверяет его.
#
# database_url: str
# Полная строка подключения к базе данных PostgreSQL.
# Содержит адрес сервера, порт, имя базы, пользователя и пароль.
# Для проекта используется асинхронный драйвер asyncpg.
# Поддерживается нормализация URL Neon:
# postgresql:// преобразуется в postgresql+asyncpg://.
# Параметр sslmode преобразуется в ssl для asyncpg,
# channel_binding удаляется из строки подключения.
#
# ==========================================================
# 2. API И ВНЕШНИЕ СЕРВИСЫ
# ==========================================================
#
# openai_api_key: SecretStr
# Основной секретный API-ключ OpenAI.
# Используется для генерации изображений, текстов,
# рецептов и других AI-функций проекта.
#
# openai_admin_api_key: SecretStr
# Административный API-ключ организации OpenAI.
# Используется для импорта фактических расходов OpenAI в CRM.
# Это отдельный ключ, не заменяющий основной API-ключ.
#
# openai_project_id: str
# Идентификатор проекта OpenAI.
# Используется вместе с административным ключом
# при получении статистики расходов проекта.
#
# spoonacular_api_key: SecretStr
# API-ключ Spoonacular.
# Предназначен для обращения к базе продуктов и рецептов,
# если соответствующие функции проекта используют этот сервис.
#
# ==========================================================
# 3. ПЕРЕКЛЮЧАТЕЛИ ГЕНЕРАЦИИ
# ==========================================================
#
# use_mock_images: bool
# Включает режим тестовых изображений.
# False — обычный режим генерации.
# True — тестовый режим, если он поддерживается вызывающим модулем.
# Не является самостоятельным переключателем всех AI-функций.
#
# ==========================================================
# 4. МОДЕЛИ OPENAI И ПАРАМЕТРЫ ГЕНЕРАЦИИ
# ==========================================================
#
# openai_image_model: str
# Название модели генерации изображений для основного продукта.
# По умолчанию: gpt-image-1.5.
#
# openai_image_size: str
# Размер генерируемого изображения.
# По умолчанию: 1024x1024.
# Фактически доступные размеры зависят от выбранной модели.
#
# openai_image_quality: str
# Уровень качества генерации основных изображений.
# По умолчанию: medium.
#
# wallpaper_image_model: str
# Модель генерации изображений для продукта Wallpaper.
# По умолчанию: gpt-image-2.5-sunburst.
#
# wallpaper_image_quality: str
# Уровень качества изображений Wallpaper.
# По умолчанию: xhigh.
#
# openai_tts_model: str
# Модель Text-to-Speech.
# Преобразует текст в голосовое аудио.
# По умолчанию: gpt-4o-mini-tts.
#
# openai_tts_voice: str
# Выбранный голос для синтеза речи.
# По умолчанию: alloy.
#
# gift_video_seconds: int
# Длительность видеоролика подарочного продукта в секундах.
# По умолчанию: 15 секунд.
# Ограничения: от 10 до 20 секунд.
#
# recipe_model: str
# Текстовая модель OpenAI для генерации рецептов.
# По умолчанию: gpt-4o-mini.
#
# ==========================================================
# 5. РАСЧЁТ СТОИМОСТИ OPENAI
# ==========================================================
#
# openai_text_input_usd_per_million: Decimal
# Стоимость одного миллиона входных текстовых токенов, USD.
# Используется для расчётной оценки расходов.
# По умолчанию: 0.15 USD.
#
# openai_text_output_usd_per_million: Decimal
# Стоимость одного миллиона выходных текстовых токенов, USD.
# По умолчанию: 0.60 USD.
#
# openai_cached_input_usd_per_million: Decimal
# Стоимость одного миллиона кешированных входных токенов, USD.
# По умолчанию: 0.075 USD.
#
# openai_image_fallback_cost_usd: Decimal
# Резервная оценка стоимости одной генерации изображения.
# Используется, если точная стоимость операции недоступна.
# По умолчанию: 0.040 USD.
#
# openai_tts_fallback_cost_usd: Decimal
# Резервная оценка стоимости синтеза речи.
# По умолчанию: 0.020 USD.
#
# openai_cost_sync_enabled: bool
# Включает автоматическую синхронизацию расходов OpenAI.
# False — синхронизация отключена.
# True — синхронизация включена, если её запускает соответствующий модуль.
#
# openai_cost_sync_interval_minutes: int
# Интервал автоматического получения расходов OpenAI, минут.
# По умолчанию: 60 минут.
# Ограничения: от 15 до 1440 минут.
#
# openai_cost_sync_days: int
# Глубина периода получения расходов OpenAI, дней.
# По умолчанию: 35 дней.
# Ограничения: от 1 до 180 дней.
#
# ==========================================================
# 6. ОСНОВНЫЕ ПАРАМЕТРЫ ПРИЛОЖЕНИЯ
# ==========================================================
#
# app_env: str
# Среда выполнения приложения.
# development — разработка.
# production — рабочая среда.
# Влияет на поведение модулей, которые проверяют это значение.
#
# log_level: str
# Уровень детализации журналирования.
# DEBUG — подробная отладочная информация.
# INFO — основные события приложения.
# WARNING — предупреждения.
# ERROR — ошибки.
# CRITICAL — критические ошибки.
#
# storage_root: Path
# Корневая папка хранения файлов проекта.
# По умолчанию: storage.
# На её основе формируются папки uploads, generated,
# cache и demo.
#
# miniapp_url: str
# Публичный HTTPS-адрес Telegram Mini App.
# Оставляется пустым до публикации приложения.
# Используется для формирования ссылок на Mini App.
#
# channel_link_secret: SecretStr
# Секрет для создания и проверки токенов внешних каналов.
# Должен быть случайным и достаточно длинным.
# Не публиковать и не передавать третьим лицам.
#
# channel_link_ttl_hours: int
# Срок действия токена подключения внешнего канала, часов.
# По умолчанию: 168 часов (7 дней).
# Ограничения: от 1 до 720 часов.
#
# miniapp_port: int
# Локальный порт веб-приложения.
# По умолчанию: 8080.
# Допустимый диапазон: 1–65535.
#
# max_upload_mb: int
# Максимальный размер загружаемого файла в мегабайтах.
# По умолчанию: 20 МБ.
# Ограничения: 1–50 МБ.
#
# image_concurrency: int
# Максимальное количество одновременных операций генерации.
# По умолчанию: 1.
# Ограничения: 1–3.
# Увеличение значения может повысить скорость обработки,
# но также увеличивает параллельную нагрузку и расходы.
#
# image_retries: int
# Количество попыток генерации изображения.
# По умолчанию: 2.
# Ограничения: 1–4.
#
# openai_quota_cooldown_seconds: int
# Пауза после ошибки квоты или лимита OpenAI, секунд.
# По умолчанию: 300 секунд (5 минут).
# Ограничения: 30–3600 секунд.
#
# enable_image_cache: bool
# Включает кеширование изображений.
# True — разрешает повторное использование кешированных результатов.
# False — отключает кеширование.
#
# ==========================================================
# 7. ОМНИКАНАЛЬНЫЕ МЕССЕНДЖЕРЫ
# ==========================================================
#
# meta_verify_token: SecretStr
# Проверочный токен Meta для подтверждения Webhook.
#
# meta_app_secret: SecretStr
# Секрет приложения Meta.
# Используется для проверки подлинности запросов Meta.
#
# meta_graph_api_version: str
# Версия Meta Graph API.
# По умолчанию: v24.0.
#
# whatsapp_access_token: SecretStr
# Токен доступа WhatsApp Business API.
#
# whatsapp_phone_number_id: str
# Идентификатор телефонного номера WhatsApp Business.
#
# messenger_page_access_token: SecretStr
# Токен доступа к странице Facebook Messenger.
#
# messenger_page_id: str
# Идентификатор Facebook-страницы, к которой подключён Messenger.
#
# instagram_access_token: SecretStr
# Токен доступа Instagram Business.
#
# instagram_business_account_id: str
# Идентификатор бизнес-аккаунта Instagram.
#
# viber_auth_token: SecretStr
# Токен авторизации Viber Bot.
#
# viber_bot_name: str
# Отображаемое имя Viber-бота.
# По умолчанию: Food Porn.
#
# slack_signing_secret: SecretStr
# Секрет Slack для проверки подлинности входящих запросов.
#
# slack_bot_token: SecretStr
# Токен Slack-приложения для работы бота.
#
# discord_public_key: str
# Публичный ключ Discord.
# Используется для проверки подлинности Interaction-запросов.
#
# Пустые учётные данные обычно означают, что соответствующий
# адаптер не настроен. Фактическое включение зависит от кода адаптера.
#
# ==========================================================
# 8. КОММЕРЧЕСКИЕ ПАРАМЕТРЫ
# ==========================================================
#
# usd_exchange_rate: float
# Расчётный курс доллара к гривне.
# По умолчанию: 41.5 UAH за 1 USD.
# Это заданное значение, а не автоматически обновляемый курс.
#
# price_electronic_uah: int
# Цена электронного продукта в гривнах.
# По умолчанию: 500 UAH.
#
# price_print_uah: int
# Цена печатного продукта в гривнах.
# По умолчанию: 1200 UAH.
#
# price_electronic_usd: int
# Цена электронного продукта в долларах.
# По умолчанию: 15 USD.
#
# price_print_usd: int
# Цена печатного продукта в долларах.
# По умолчанию: 35 USD.
#
# menu_price: float
# Основная цена меню.
# По умолчанию: 500.0.
# Должна быть больше нуля.
#
# currency: str
# Валюта основной цены меню.
# По умолчанию: UAH.
#
# menu_price_stars: int
# Стоимость меню в Telegram Stars.
# По умолчанию: 0.
# Ограничения: 0–100000.
# Значение 0 может означать, что цена не настроена.
#
# gift_price_stars: int
# Стоимость подарочного продукта в Telegram Stars.
# По умолчанию: 0.
# Ограничения: 0–100000.
#
# ВНИМАНИЕ:
# В проекте одновременно присутствуют несколько ценовых полей.
# Не следует считать их взаимозаменяемыми без проверки модулей,
# которые используют каждое конкретное поле.
#
# ==========================================================
# 9. PORTMONE — ПЛАТЁЖНЫЙ ШЛЮЗ
# ==========================================================
#
# portmone_gateway_url: str
# Адрес платёжного шлюза Portmone.
# В текущем коде по умолчанию указан URL документации.
# Перед реальной оплатой необходимо проверить,
# какой URL ожидает используемый платёжный модуль.
#
# portmone_payee_id: str
# Идентификатор получателя платежей Portmone.
# Выдаётся платёжным сервисом.
#
# portmone_login: str
# Логин магазина Portmone.
#
# portmone_password: SecretStr
# Пароль магазина Portmone.
# Хранить только в защищённом окружении.
#
# portmone_test_mode: bool
# Включает диагностический тестовый режим Portmone.
# False — тестовый режим выключен.
# Не включать диагностическую оплату в рабочем окружении.
#
# portmone_test_amount_uah: Decimal
# Тестовая сумма платежа в гривнах.
# По умолчанию: 1.00 UAH.
# Допустимо: больше 0 и не более 100 UAH.
#
# ==========================================================
# 10. MONOBANK — ИНТЕРНЕТ-ЭКВАЙРИНГ
# ==========================================================
#
# mono_token: SecretStr
# Токен интернет-эквайринга Monobank.
# Получается в кабинете продавца.
#
# mono_redirect_url: str
# URL возврата клиента после завершения оплаты.
#
# mono_webhook_url: str
# Публичный URL для получения уведомлений Monobank
# об изменении состояния платежа.
#
# ==========================================================
# 11. WAYFORPAY — ПЛАТЁЖНЫЙ ШЛЮЗ
# ==========================================================
#
# public_base_url: str
# Публичный базовый HTTPS-адрес приложения.
# Используется при формировании платёжных и callback-ссылок.
#
# wayforpay_merchant_account: str
# Идентификатор магазина WayForPay.
#
# wayforpay_merchant_secret_key: SecretStr
# Секретный ключ магазина WayForPay.
# Используется для формирования и проверки подписи платежей.
#
# wayforpay_merchant_domain: str
# Домен магазина, зарегистрированный в WayForPay.
#
# wayforpay_test_mode: bool
# Включает тестовый режим WayForPay.
# False — обычный рабочий режим.
#
# wayforpay_menu_price_uah: Decimal
# Настроенная сумма тестовой/платёжной операции для меню.
# По умолчанию: 5.00 UAH.
# Ограничения: больше 0 и не более 100000 UAH.
#
# wayforpay_wallpaper_price_uah: Decimal
# Настроенная сумма тестовой/платёжной операции Wallpaper.
# По умолчанию: 1.00 UAH.
# Ограничения: больше 0 и не более 100000 UAH.
#
# ==========================================================
# 12. ТИПОГРАФИЯ И ПЕЧАТЬ
# ==========================================================
#
# printshop_email: str
# Email типографии для отправки заказов.
#
# printshop_name: str
# Название типографии.
# По умолчанию: Студия Печати 'ArtPress'.
#
# print_poster_width_mm: int
# Ширина печатного постера в миллиметрах.
# По умолчанию: 300 мм.
#
# print_poster_height_mm: int
# Высота печатного постера в миллиметрах.
# По умолчанию: 400 мм.
#
# print_dpi: int
# Разрешение печатного изображения в DPI.
# По умолчанию: 300 DPI.
# Более высокое значение увеличивает требования к разрешению файла.
#
# ==========================================================
# 13. SMTP — ОТПРАВКА EMAIL
# ==========================================================
#
# smtp_host: str
# Адрес SMTP-сервера почтового провайдера.
#
# smtp_port: int
# Порт SMTP-сервера.
# По умолчанию: 465.
# Ограничения: 1–65535.
#
# smtp_user: str
# Логин почтового аккаунта.
# Обычно совпадает с адресом электронной почты.
#
# smtp_password: SecretStr
# Пароль почтового аккаунта или пароль приложения.
#
# smtp_use_tls: bool
# Использование защищённого соединения SMTP.
# True — TLS включён.
# False — выключен.
# Конкретный режим соединения должен соответствовать настройкам
# SMTP-провайдера и реализации почтового клиента.
#
# ==========================================================
# 14. ШАБЛОН ПИСЬМА В ТИПОГРАФИЮ
# ==========================================================
#
# printshop_email_template: str
# Шаблон письма, отправляемого в типографию.
# Содержит переменные, которые заменяются данными заказа:
#
# {user_id}    — Telegram User ID клиента.
# {username}   — Telegram username клиента.
# {phone}      — телефон клиента.
# {city}       — город клиента.
# {country}    — страна клиента.
# {width}      — ширина постера в миллиметрах.
# {height}     — высота постера в миллиметрах.
# {dpi}        — разрешение печати.
# {file_path}  — путь к файлу для печати.
#
# При изменении шаблона необходимо сохранять имена переменных,
# которые ожидает функция форматирования письма.
#
# ==========================================================
# 15. АДМИНИСТРАТИВНЫЙ ДОСТУП И CRM
# ==========================================================
#
# admin_telegram_ids: tuple[int, ...]
# Список Telegram ID пользователей, которым разрешён
# административный доступ к CRM через Telegram.
# Можно указать несколько ID.
# В .env формат:
# ADMIN_TELEGRAM_IDS=725003786,123456789
# Допускается также JSON-массив целых чисел.
#
# crm_vip_telegram_ids: tuple[int, ...]
# VIP с правом входа в Mini CRM (режим только обзора) по Telegram ID.
# Не путать с VIP для бесплатной генерации по username.
# CRM_VIP_TELEGRAM_IDS=123456789,987654321
#
# free_generation_telegram_ids: tuple[int, ...]
# Список Telegram ID пользователей, которым разрешена
# бесплатная генерация.
# Это отдельный список, не заменяющий администраторский.
#
# default_vip_users: list[str]
# Список Telegram username пользователей с VIP-статусом.
# По умолчанию:
# Voloshka0602, MenuDishesForLove, bondarev_e.
# Это VIP-список, а не список администраторов CRM.
#
# admin_username: str
# Имя пользователя для входа в веб-панель администратора.
#
# admin_password: SecretStr
# Пароль для входа в веб-панель администратора.
# Рекомендуется использовать длинный уникальный пароль.
#
# admin_session_secret: SecretStr
# Секрет подписи браузерных сессий администратора.
# Должен быть случайным и постоянным.
# Если изменить его, существующие сессии могут стать недействительными.
#
# crm_encryption_key: SecretStr
# Ключ шифрования API-ключей и учётных данных интеграций CRM.
# Используется Fernet.
# Не менять после сохранения зашифрованных данных без процедуры
# расшифровки старым ключом и повторного шифрования новым.
#
# ==========================================================
# 16. СЛУЖЕБНЫЕ ПАПКИ STORAGE
# ==========================================================
#
# uploads_dir
# Свойство, формирующее путь storage/uploads.
# Используется для загруженных пользователями файлов.
#
# generated_dir
# Свойство, формирующее путь storage/generated.
# Используется для созданных изображений и документов.
#
# cache_dir
# Свойство, формирующее путь storage/cache.
# Используется для кешированных данных.
#
# demo_dir
# Свойство, формирующее путь storage/demo.
# Используется для демонстрационных материалов.
#
# ensure_directories()
# Создаёт перечисленные выше папки, если они отсутствуют.
#
# validate_runtime()
# Выполняет базовую проверку обязательных параметров запуска.
# В текущей реализации проверяет наличие BOT_TOKEN
# и отсутствие стандартного значения replace_me.
#
# ==========================================================
# 17. ЗАГРУЗКА КОНФИГУРАЦИИ
# ==========================================================
#
# model_config
# Настройки загрузки Pydantic Settings:
#
# env_file=".env"
# Файл, из которого загружаются переменные окружения.
#
# env_file_encoding="utf-8"
# Кодировка файла .env.
#
# case_sensitive=False
# Имена переменных окружения нечувствительны к регистру.
#
# extra="ignore"
# Неизвестные переменные .env игнорируются.
#
# get_settings()
# Возвращает экземпляр Settings.
# Использует lru_cache(maxsize=1), поэтому настройки
# загружаются один раз и кешируются в процессе приложения.
#
# ==========================================================
# 18. ЭКСПОРТИРУЕМЫЕ КОНСТАНТЫ МОДУЛЯ
# ==========================================================
#
# USD_EXCHANGE_RATE
# Глобальная константа курса USD/UAH.
#
# PRICE_ELECTRONIC_UAH
# Глобальная константа цены электронного продукта в UAH.
#
# PRICE_PRINT_UAH
# Глобальная константа цены печатного продукта в UAH.
#
# PRICE_ELECTRONIC_USD
# Глобальная константа цены электронного продукта в USD.
#
# PRICE_PRINT_USD
# Глобальная константа цены печатного продукта в USD.
#
# PORTMONE_GATEWAY_URL
# Глобальная константа URL Portmone.
#
# PRINT_SHOP_EMAIL
# Глобальный адрес электронной почты типографии.
#
# PRINT_SHOP_EMAIL_TEMPLATE
# Глобальный шаблон письма для типографии.
#
# PRINT_POSTER_WIDTH_MM
# Глобальная ширина постера в миллиметрах.
#
# PRINT_POSTER_HEIGHT_MM
# Глобальная высота постера в миллиметрах.
#
# PRINT_DPI
# Глобальное разрешение печати.
#
# ВНИМАНИЕ:
# Глобальные константы в конце файла заданы отдельно
# от полей Settings. Изменение значения в .env само по себе
# не изменяет эти константы.
# Если разные модули используют разные источники цен,
# курса или email, значения могут расходиться.
#
# ==========================================================
# КОНЕЦ СПРАВОЧНИКА
# ==========================================================
