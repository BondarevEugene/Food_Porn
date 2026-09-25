"""
==========================================================
FOOD_PORN

Module: Runtime Configuration
Layer: Application Core

Responsibilities:
    - Load environment variables and `.env` values
    - Validate and normalize external configuration
    - Provide storage paths, printshop, and payment gateway settings
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
    database_url: str = "postgresql+asyncpg://neondb_owner:npg_secret@ep-young-sea.aws.neon.tech/neondb?sslmode=require"

    # APIs
    openai_api_key: SecretStr = SecretStr("replace_me")
    spoonacular_api_key: SecretStr = SecretStr("replace_me")  # Ключ для кулинарного API Spoonacular

    # Generation Toggles
    use_mock_images: bool = Field(default=False)  # Если True, не использует API, а берет картинку-заглушку

    # OpenAI Settings
    openai_image_model: str = "gpt-image-1.5"
    openai_image_size: str = "1024x1024"
    openai_image_quality: str = "medium"

    # Application Configuration
    app_env: str = "development"
    log_level: str = "INFO"
    storage_root: Path = Path("storage")
    max_upload_mb: int = Field(default=20, ge=1, le=50)
    image_concurrency: int = Field(default=1, ge=1, le=3)
    image_retries: int = Field(default=2, ge=1, le=4)
    openai_quota_cooldown_seconds: int = Field(default=300, ge=30, le=3600)
    enable_image_cache: bool = True

    # --- Коммерческие настройки: Цена и валюта ---
    menu_price: float = Field(default=499.00, ge=0.0)
    currency: str = Field(default="UAH")

    # --- Настройки типографии для отправки готовых макетов ---
    printshop_email: str = Field(default="bondarev.e.1707@gmail.com")
    printshop_name: str = Field(default="Студия Печати 'ArtPress'")

    # --- Платежный шлюз: Portmone ---
    portmone_payee_id: str = Field(default="replace_me")
    portmone_login: str = Field(default="replace_me")
    portmone_password: SecretStr = SecretStr("replace_me")

    # --- Платежный шлюз: Redsys ---
    redsys_merchant_code: str = Field(default="replace_me")
    redsys_terminal: str = Field(default="001")
    redsys_secret_key: SecretStr = SecretStr("replace_me")
    redsys_currency: str = Field(default="978")  # EUR

    # Admins
    admin_telegram_ids: Annotated[tuple[int, ...], NoDecode] = ()

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

    @field_validator("admin_telegram_ids", mode="before")
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