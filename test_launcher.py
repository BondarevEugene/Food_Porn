"""
==========================================================
FOOD_PORN

Module: Launcher Diagnostics Tests
Layer: Test

Responsibilities:
    - Verify secret masking in diagnostic output
    - Verify safe database labels
    - Verify health scoring and critical-failure detection
==========================================================
"""

from launcher import (
    CheckResult,
    Status,
    calculate_health,
    has_critical_failures,
    mask_secret,
    safe_database_label,
    safe_text,
)


def test_mask_secret_never_returns_complete_value() -> None:
    secret = "sk-example-super-secret-value"

    masked = mask_secret(secret)

    assert secret not in masked
    assert masked.startswith("sk-e")
    assert masked.endswith("lue")


def test_database_label_hides_username_and_password() -> None:
    url = "postgresql+asyncpg://owner:password@db.example.test/neondb?ssl=require"

    label = safe_database_label(url)

    assert "owner" not in label
    assert "password" not in label
    assert "db.example.test" in label
    assert label.endswith("/neondb")


def test_safe_text_masks_credentials_in_database_error() -> None:
    error = "cannot connect postgresql+asyncpg://owner:very-secret@db.example.test/neondb"

    sanitized = safe_text(error)

    assert "very-secret" not in sanitized
    assert "***@db.example.test" in sanitized


def test_safe_text_masks_telegram_token_without_label() -> None:
    token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_123456789"

    sanitized = safe_text(f"request failed for {token}")

    assert token not in sanitized
    assert "TELEGRAM_TOKEN" in sanitized


def test_health_score_uses_critical_weight() -> None:
    results = [
        CheckResult("A", "pass", Status.PASS, "ok", critical=True),
        CheckResult("B", "warning", Status.WARN, "warning"),
        CheckResult("C", "skipped", Status.SKIP, "skipped"),
    ]

    assert calculate_health(results) == 88


def test_only_critical_failure_blocks_start() -> None:
    ordinary_failure = CheckResult("A", "optional", Status.FAIL, "failed")
    critical_failure = CheckResult("B", "required", Status.FAIL, "failed", critical=True)

    assert not has_critical_failures([ordinary_failure])
    assert has_critical_failures([ordinary_failure, critical_failure])
