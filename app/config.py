"""
==========================================================
FOOD_PORN & OLD MONEY MANIFESTATIONS

Module: Runtime Configuration
Layer: Application Core
==========================================================
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # Telegram & Database
    bot_token: str = "replace_me"
    database_url: str = "postgresql+asyncpg://USER:PASSWORD@localhost/DATABASE"

    # APIs
    openai_api_key: SecretStr = SecretStr("replace_me")
    spoonacular_api_key: SecretStr = SecretStr("replace_me")

    # Generation Toggles
    use_mock_images: bool = Field(default=False)

    # OpenAI Settings
    openai_image_model: str = "gpt-image-1.5"
    openai_image_size: str = "1024x1024"
    openai_image_quality: str = "medium"
    wallpaper_image_model: str = "gpt-image-2.5-sunburst"
    wallpaper_image_quality: str = "xhigh"

    # Application Configuration
    app_env: str = "development"
    log_level: str = "INFO"
    storage_root: Path = Path("storage")
    # Public HTTPS address of the Telegram Mini App. Leave empty until deployed.
    miniapp_url: str = ""
    miniapp_port: int = Field(default=8080, ge=1, le=65535)
    max_upload_mb: int = Field(default=20, ge=1, le=50)
    image_concurrency: int = Field(default=1, ge=1, le=3)
    image_retries: int = Field(default=2, ge=1, le=4)
    openai_quota_cooldown_seconds: int = Field(default=300, ge=30, le=3600)
    enable_image_cache: bool = True

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

    # Портмоне платіжний шлюз
    portmone_gateway_url: str = Field(default="https://docs.portmone.com.ua/docs/uk/PaymentGatewayUa/")
    portmone_payee_id: str = Field(default="replace_me")
    portmone_login: str = Field(default="replace_me")
    portmone_password: SecretStr = SecretStr("replace_me")

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
    free_generation_telegram_ids: Annotated[tuple[int, ...], NoDecode] = ()
    default_vip_users: list[str] = Field(default_factory=lambda: ["Voloshka0602", "MenuDishesForLove", "bondarev_e"])
    admin_username: str = ""
    admin_password: SecretStr = SecretStr("")
    admin_session_secret: SecretStr = SecretStr("")

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
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @field_validator("admin_telegram_ids", "free_generation_telegram_ids", mode="before")
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
