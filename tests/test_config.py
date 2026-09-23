"""
==========================================================
FOOD_PORN

Module: Configuration Tests
Layer: Test

Responsibilities:
    - Verify optional administrator ID parsing
    - Verify safe OpenAI request defaults
==========================================================
"""

from app.config import Settings


def test_empty_admin_ids_from_env_is_allowed(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "")
    settings = Settings(_env_file=None)
    assert settings.admin_telegram_ids == ()


def test_comma_separated_admin_ids_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "123, 456")
    settings = Settings(_env_file=None)
    assert settings.admin_telegram_ids == (123, 456)


def test_json_admin_ids_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "[]")
    assert Settings(_env_file=None).admin_telegram_ids == ()

    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "[123, 456]")
    assert Settings(_env_file=None).admin_telegram_ids == (123, 456)


def test_safe_image_request_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.image_concurrency == 1
    assert settings.image_retries == 2
    assert settings.openai_quota_cooldown_seconds == 300
