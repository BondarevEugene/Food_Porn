"""
==========================================================
FOOD_PORN • CONFIGURATION MANAGEMENT (Pydantic Settings)
==========================================================
"""

from __future__ import annotations

from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    bot_token: str = Field(default="replace_me", validation_alias="BOT_TOKEN")
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/food_porn",
        validation_alias="DATABASE_URL",
    )
    miniapp_port: int = Field(default=8081, validation_alias="MINIAPP_PORT")
    miniapp_url: str | None = Field(default=None, validation_alias="MINIAPP_URL")
    admin_username: str = Field(default="admin", validation_alias="ADMIN_USERNAME")
    admin_password: SecretStr = Field(default=SecretStr("foodporn_secret"), validation_alias="ADMIN_PASSWORD")

    # Business pricing & parameters
    usd_exchange_rate: float = Field(default=41.5, validation_alias="USD_EXCHANGE_RATE")
    price_electronic_uah: int = Field(default=500, validation_alias="PRICE_ELECTRONIC_UAH")
    price_print_uah: int = Field(default=1500, validation_alias="PRICE_PRINT_UAH")
    price_electronic_usd: float = Field(default=15.0, validation_alias="PRICE_ELECTRONIC_USD")
    price_print_usd: float = Field(default=45.0, validation_alias="PRICE_PRINT_USD")
    menu_price_stars: int = Field(default=100, validation_alias="MENU_PRICE_STARS")
    gift_price_stars: int = Field(default=150, validation_alias="GIFT_PRICE_STARS")
    printshop_name: str = Field(default="FoodPorn Print", validation_alias="PRINTSHOP_NAME")
    printshop_email: str = Field(default="print@foodporn.example", validation_alias="PRINTSHOP_EMAIL")
    portmone_payee_id: str = Field(default="123456", validation_alias="PORTMONE_PAYEE_ID")
    use_mock_images: bool = Field(default=True, validation_alias="USE_MOCK_IMAGES")
    storage_root: str = Field(default="storage", validation_alias="STORAGE_ROOT")

    def validate_runtime(self) -> None:
        pass

    def ensure_directories(self) -> None:
        import pathlib
        pathlib.Path(self.storage_root).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()