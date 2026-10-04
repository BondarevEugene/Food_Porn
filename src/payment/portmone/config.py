from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class PortmoneConfig(BaseSettings):
    payee_id: str = Field(default="111111", validation_alias="PORTMONE_PAYEE_ID")
    login: str = Field(default="TEST", validation_alias="PORTMONE_LOGIN")
    password: str = Field(default="test_secret", validation_alias="PORTMONE_PASSWORD")
    secret_key: str = Field(default="test_secret_key", validation_alias="PORTMONE_SECRET_KEY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

portmone_settings = PortmoneConfig()