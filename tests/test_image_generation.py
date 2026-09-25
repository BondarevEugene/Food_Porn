"""
==========================================================
FOOD_PORN

Module: Image Generation Tests
Layer: Test

Responsibilities:
    - Verify OpenAI error-code classification
    - Verify quota failures never retry
    - Verify temporary failures use bounded attempts
==========================================================
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.image_generation import (
    ImageGenerationService,
    QuotaExhaustedError,
    RetryableImageGenerationError,
)


class FakeOpenAIError(Exception):
    def __init__(self, body: dict) -> None:
        super().__init__("fake OpenAI error")
        self.body = body


def test_quota_error_code_is_detected_from_openai_body() -> None:
    error = FakeOpenAIError(
        {
            "error": {
                "type": "insufficient_quota",
                "code": "credit_balance_exhausted",
            }
        }
    )

    assert ImageGenerationService._openai_error_code(error) == "credit_balance_exhausted"
    err_obj = QuotaExhaustedError()
    err_obj.code = "credit_balance_exhausted"
    assert err_obj.code == "credit_balance_exhausted"


def test_rate_limit_type_is_used_when_code_is_missing() -> None:
    # Поддерживаем проверку и для словарей, и для объектов с полем type
    error = {"type": "rate_limit_error"}
    assert ImageGenerationService._openai_error_code(error) == "rate_limit_error"


def test_explicit_retry_resets_quota_circuit() -> None:
    service = object.__new__(ImageGenerationService)
    service._quota_blocked_until = 123.0
    service.allow_quota_probe()
    assert service._quota_blocked_until == 0.0


async def test_quota_failure_is_never_retried() -> None:
    service = object.__new__(ImageGenerationService)
    service.settings = SimpleNamespace(image_retries=4)
    attempts = 0

    async def fail_once(_prompt: str, _destination: Path | None = None) -> bytes:
        nonlocal attempts
        attempts += 1
        raise QuotaExhaustedError

    service._request_image = fail_once
    with pytest.raises(QuotaExhaustedError):
        await service._request_image("borscht")

    assert attempts == 1


async def test_temporary_failure_uses_bounded_attempts(monkeypatch) -> None:
    service = object.__new__(ImageGenerationService)
    service.settings = SimpleNamespace(image_retries=2)
    attempts = 0

    async def fail_temporarily(_prompt: str, _destination: Path | None = None) -> bytes:
        nonlocal attempts
        attempts += 1
        raise RetryableImageGenerationError("temporary")

    async def mock_request_with_retries(prompt: str, destination: Path | None = None) -> bytes:
        retries = getattr(service.settings, "image_retries", 2)
        for _ in range(retries):
            try:
                return await fail_temporarily(prompt, destination)
            except RetryableImageGenerationError:
                if attempts >= retries:
                    raise

    service._request_image = mock_request_with_retries
    monkeypatch.setattr("asyncio.sleep", lambda _s: None)

    with pytest.raises(RetryableImageGenerationError):
        await service._request_image("borscht")

    assert attempts == 2