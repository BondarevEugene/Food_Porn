"""
==========================================================
FOOD_PORN

Module: Runtime Configuration
Layer: Application Core

Responsibilities:
    - Load environment variables and `.env` values
    - Validate and normalize external configuration
    - Provide storage paths and runtime safety checks
==========================================================
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from pydantic import Field, field_validator, SecretStr


class Settings(BaseSettings):
    # Telegram & Database
    bot_token: str = "replace_me"
    database_url: str = "postgresql+asyncpg://neondb_owner:npg_secret@ep-young-sea.aws.neon.tech/neondb?sslmode=require"

    # APIs
    openai_api_key: SecretStr = SecretStr("replace_me")
    spoonacular_api_key: SecretStr = SecretStr("replace_me")  # Ключ для кулинарного API Spoonacular

    # Generation Toggles
    use_mock_images: bool = Field(default=False)  # Если True, не использует API, а берет картинку-заглушку

    # OpenAI Settings (оставлены на случай возврата к генерации ИИ в будущем)
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
        # Для Spoonacular пока не требуем жестко, если включены моки
        if not self.use_mock_images and (not self.spoonacular_api_key or self.spoonacular_api_key == "replace_me"):
            pass  # Выведем предупреждение в сервисе
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
