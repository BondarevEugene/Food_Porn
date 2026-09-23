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
    assert QuotaExhaustedError().code == "credit_balance_exhausted"


def test_rate_limit_type_is_used_when_code_is_missing() -> None:
    error = FakeOpenAIError({"type": "rate_limit_error"})
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

    async def fail_once(_prompt: str) -> bytes:
        nonlocal attempts
        attempts += 1
        raise QuotaExhaustedError

    service._request_once = fail_once
    with pytest.raises(QuotaExhaustedError):
        await service._request_image("borscht")

    assert attempts == 1


async def test_temporary_failure_uses_bounded_attempts(monkeypatch) -> None:
    service = object.__new__(ImageGenerationService)
    service.settings = SimpleNamespace(image_retries=2)
    attempts = 0

    async def fail_temporarily(_prompt: str) -> bytes:
        nonlocal attempts
        attempts += 1
        raise RetryableImageGenerationError("temporary")

    async def no_wait(_seconds: float) -> None:
        return None

    service._request_once = fail_temporarily
    monkeypatch.setattr("app.services.image_generation.asyncio.sleep", no_wait)

    with pytest.raises(RetryableImageGenerationError):
        await service._request_image("borscht")

    assert attempts == 2
