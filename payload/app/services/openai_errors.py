"""One retry policy and safe diagnostics for every OpenAI service in the bot."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TypeVar

import httpx
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError

logger = logging.getLogger(__name__)
T = TypeVar("T")
QUOTA_CODES = {
    "credit_balance_exhausted",
    "insufficient_quota",
    "billing_hard_limit_reached",
    "billing_not_active",
    "organization_spend_limit_exceeded",
    "project_spend_limit_exceeded",
    "organization_usage_limit_exceeded",
}
SAFETY_CODES = {"moderation_blocked", "content_policy_violation", "safety_violation"}
MAX_AUTO_WAIT = 30.0


def safe_identifier(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value):
        return value
    return None


@dataclass(frozen=True)
class AIProblem:
    kind: str
    code: str
    status: int | None = None
    request_id: str | None = None
    retry_after: float | None = None


class OpenAIServiceError(RuntimeError):
    """Safe to store in an order; never contains API response text or inputs."""

    def __init__(self, problem: AIProblem):
        self.problem = problem
        self.code = problem.code
        super().__init__(operator_message(problem))


def operator_message(problem: AIProblem) -> str:
    actions = {
        "credit_balance_exhausted": "Пополните API-баланс организации OpenAI.",
        "organization_spend_limit_exceeded": "Проверьте лимит расходов организации OpenAI.",
        "project_spend_limit_exceeded": "Проверьте лимит расходов проекта OpenAI.",
        "organization_usage_limit_exceeded": "Проверьте разрешённый лимит использования организации OpenAI.",
        "billing_not_active": "Активируйте оплату API в OpenAI Billing.",
    }
    fallback = {
        "quota": "Проверьте API-баланс и лимиты проекта/организации OpenAI.",
        "auth": "Проверьте OPENAI_API_KEY и принадлежность ключа проекту.",
        "access": "Проверьте доступ проекта и ключа к модели/операции.",
        "config": "Проверьте модель и параметры запроса OpenAI.",
        "request": "Проверьте параметры запроса; этот отказ не повторяется автоматически.",
        "safety": "Сервис отклонил входные данные; выберите другое фото или уточните формулировку.",
        "rate_limit": "Снизьте частоту запросов и повторите после паузы.",
        "timeout": "Ответ не получен вовремя. Для изображений автоматический повтор отключён: результат первого запроса неизвестен.",
        "connection": "Проверьте соединение с OpenAI; результат запроса изображения может быть неизвестен.",
        "server": "Временная ошибка OpenAI. Повторите после паузы.",
        "storage": "Не удалось сохранить изображение. Проверьте место и права записи в storage.",
        "invalid_response": "OpenAI вернул неполный результат; незавершённый заказ не выдаётся.",
    }
    text = actions.get(problem.code, fallback.get(problem.kind, "Проверьте журнал приложения."))
    suffix = f" request_id={problem.request_id}" if problem.request_id else ""
    return f"OpenAI [{problem.kind}/{problem.code}]{suffix}: {text}"


def user_message(problem: AIProblem, language: str = "uk") -> str:
    language = getattr(language, "value", language)
    language = (
        "ru"
        if str(language).lower().startswith("ru")
        else "en"
        if str(language).lower().startswith("en")
        else "uk"
    )
    phrases = {
        "storage": (
            "Не вдалося зберегти результат на сервері. Адміністратору потрібно перевірити сховище.",
            "Не удалось сохранить результат на сервере. Администратору нужно проверить хранилище.",
            "The result could not be saved on the server. The administrator needs to check storage.",
        ),
        "interrupted": (
            "Створення перервано під час зупинки бота. Можна продовжити з історії замовлень.",
            "Создание прервано при остановке бота. Можно продолжить из истории заказов.",
            "Creation was interrupted when the bot stopped. Resume from your order history.",
        ),
        "quota": (
            "Генерацію призупинено через обмеження сервісу. Потрібна перевірка оплати або лімітів адміністратором.",
            "Генерация приостановлена из-за ограничения сервиса. Администратору нужно проверить оплату или лимиты.",
            "Generation is paused because of a service allowance issue. The administrator needs to check billing or limits.",
        ),
        "auth": (
            "Генерація недоступна через налаштування доступу. Адміністратору потрібно перевірити ключ сервісу.",
            "Генерация недоступна из-за настроек доступа. Администратору нужно проверить ключ сервиса.",
            "Generation is unavailable because of access settings. The administrator needs to check the service key.",
        ),
        "access": (
            "Немає доступу до потрібної моделі. Адміністратору потрібно перевірити дозволи сервісу.",
            "Нет доступа к нужной модели. Администратору нужно проверить разрешения сервиса.",
            "The required model is unavailable. The administrator needs to check service permissions.",
        ),
        "config": (
            "Сервіс відхилив налаштування генерації. Потрібна перевірка адміністратором.",
            "Сервис отклонил настройки генерации. Нужна проверка администратором.",
            "The service rejected the generation settings. The administrator needs to check them.",
        ),
        "safety": (
            "Фото або формулювання не пройшли перевірку сервісу. Спробуйте інше фото або уточніть текст.",
            "Фото или формулировка не прошли проверку сервиса. Попробуйте другое фото или уточните текст.",
            "A photo or wording did not pass the service check. Try another photo or revise the text.",
        ),
        "rate_limit": (
            "Сервіс обмежив частоту запитів. Генерацію призупинено; повторіть після паузи.",
            "Сервис ограничил частоту запросов. Генерация приостановлена; повторите после паузы.",
            "The service limited request frequency. Generation is paused; retry after a short wait.",
        ),
        "timeout": (
            "Сервіс не відповів вчасно. Автоматичний повтор зупинено, щоб не створити дубль. Можна продовжити пізніше.",
            "Сервис не ответил вовремя. Автоматический повтор остановлен, чтобы не создать дубль. Можно продолжить позже.",
            "The service did not reply in time. Automatic retries stopped to avoid a duplicate. You can resume later.",
        ),
    }
    generic = (
        "Не вдалося завершити генерацію через помилку сервісу. Можна повторити пізніше.",
        "Не удалось завершить генерацию из-за ошибки сервиса. Можно повторить позже.",
        "Generation could not finish because of a service error. You can retry later.",
    )
    result = phrases.get(problem.kind, generic)[{"uk": 0, "ru": 1, "en": 2}[language]]
    if problem.kind == "rate_limit" and problem.retry_after is not None:
        seconds = max(1, math.ceil(problem.retry_after))
        result += {
            "uk": f" Пауза: щонайменше {seconds} с.",
            "ru": f" Пауза: не меньше {seconds} с.",
            "en": f" Wait at least {seconds} s.",
        }[language]
    return result


def _retry_after(error: object) -> float | None:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {})
    value = headers.get("retry-after-ms") or headers.get("retry-after")
    if value is None:
        return None
    try:
        delay = float(value)
        if headers.get("retry-after-ms") is not None:
            delay /= 1000
    except (ValueError, TypeError):
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=UTC)
            delay = (date - datetime.now(UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0.0, delay) if math.isfinite(delay) else None


def classify_openai_error(error: object) -> AIProblem:
    if isinstance(error, OpenAIServiceError):
        return error.problem
    body = getattr(error, "body", {})
    details = body.get("error", body) if isinstance(body, dict) else {}
    details = details if isinstance(details, dict) else {}
    code = safe_identifier(details.get("code")) or safe_identifier(getattr(error, "code", None))
    error_type = safe_identifier(details.get("type")) or safe_identifier(
        getattr(error, "type", None)
    )
    status = getattr(error, "status_code", None)
    status = status if isinstance(status, int) else None
    request_id = safe_identifier(getattr(error, "request_id", None))
    code = code or error_type or type(error).__name__
    if code in QUOTA_CODES or error_type == "insufficient_quota":
        kind = "quota"
    elif isinstance(error, APITimeoutError) or isinstance(error, httpx.TimeoutException):
        kind = "timeout"
    elif isinstance(error, (APIConnectionError, httpx.TransportError)):
        kind = "connection"
    elif code in SAFETY_CODES:
        kind = "safety"
    elif status == 401:
        kind = "auth"
    elif status == 403:
        kind = "access"
    elif status == 404 or code in {"model_not_found", "invalid_api_key", "unsupported_model"}:
        kind = "auth" if code == "invalid_api_key" else "config"
    elif status == 429:
        kind = "rate_limit"
    elif status is not None and status >= 500:
        kind = "server"
    elif status in {400, 422}:
        kind = "request"
    elif status == 408:
        kind = "timeout"
    elif status == 409:
        kind = "server"
    else:
        kind = "unknown"
    return AIProblem(kind, code, status, request_id, _retry_after(error))


@dataclass
class _Circuit:
    problem: AIProblem
    until: float
    probe_running: bool = False


# Billing/auth failures concern the same credential across menu, gift and text calls.
# Keys are one-way fingerprints; no raw credentials or customer inputs are retained.
_circuits: dict[str, _Circuit] = {}
_rate_blocks: dict[tuple[str, str], _Circuit] = {}


def _fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def reset_openai_access(api_key: str) -> None:
    """Explicit operator probe after fixing credentials or billing."""
    _circuits.pop(_fingerprint(api_key), None)
    for key in list(_rate_blocks):
        if key[0] == _fingerprint(api_key):
            _rate_blocks.pop(key)


def check_openai_access(api_key: str) -> _Circuit | None:
    if api_key in ("", "replace_me"):
        raise OpenAIServiceError(AIProblem("auth", "missing_api_key"))
    state = _circuits.get(_fingerprint(api_key))
    if state is None:
        return None
    remaining = state.until - time.monotonic()
    if remaining > 0 or state.probe_running:
        raise OpenAIServiceError(replace(state.problem, retry_after=max(1, remaining)))
    return state


async def request_openai(
    request: Callable[[], Awaitable[T]],
    *,
    api_key: str,
    operation: str,
    attempts: int = 2,
    image_request: bool = False,
    quota_cooldown: int = 300,
    preserve_safety: bool = False,
) -> T:
    """Own retries; callers must construct the SDK client with max_retries=0."""
    identity = _fingerprint(api_key)
    rate_key = (identity, operation)
    rate_block = _rate_blocks.get(rate_key)
    if rate_block is not None and rate_block.until > time.monotonic():
        raise OpenAIServiceError(
            replace(rate_block.problem, retry_after=rate_block.until - time.monotonic())
        )
    probe = check_openai_access(api_key)
    if probe is not None:
        probe.probe_running = True
    try:
        for attempt in range(max(1, min(attempts, 4))):
            # An already-running peer may have discovered quota since our first attempt.
            current = _circuits.get(identity)
            if current is not None and current is not probe:
                check_openai_access(api_key)
            try:
                result = await request()
            except (APIError, httpx.TransportError) as error:
                problem = classify_openai_error(error)
                delay = (
                    problem.retry_after
                    if problem.retry_after is not None
                    else min(2**attempt + random.random(), 8)
                )
                if problem.kind == "rate_limit":
                    problem = replace(problem, retry_after=delay)
                    if len(_rate_blocks) >= 256 and rate_key not in _rate_blocks:
                        oldest = min(_rate_blocks, key=lambda key: _rate_blocks[key].until)
                        _rate_blocks.pop(oldest)
                    _rate_blocks[rate_key] = _Circuit(problem, time.monotonic() + delay)
                logger.warning(
                    "OpenAI failure operation=%s kind=%s code=%s status=%s request_id=%s attempt=%s; %s",
                    operation,
                    problem.kind,
                    problem.code,
                    problem.status,
                    problem.request_id or "unknown",
                    attempt + 1,
                    operator_message(problem),
                )
                if problem.kind in {"quota", "auth"}:
                    if len(_circuits) >= 128 and identity not in _circuits:
                        oldest = min(_circuits, key=lambda key: _circuits[key].until)
                        _circuits.pop(oldest)
                    _circuits[identity] = _Circuit(
                        problem, time.monotonic() + max(30, quota_cooldown)
                    )
                if (
                    preserve_safety
                    and problem.code == "moderation_blocked"
                    and isinstance(error, APIStatusError)
                ):
                    raise
                retryable = problem.kind in {"rate_limit", "server", "connection", "timeout"}
                if image_request and problem.kind in {"connection", "timeout"}:
                    retryable = False
                if (
                    not retryable
                    or attempt + 1 >= max(1, min(attempts, 4))
                    or delay > MAX_AUTO_WAIT
                ):
                    raise OpenAIServiceError(problem) from None
                await asyncio.sleep(delay)
                continue
            if probe is not None and _circuits.get(identity) is probe:
                _circuits.pop(identity)
            _rate_blocks.pop(rate_key, None)
            return result
    finally:
        if probe is not None:
            probe.probe_running = False
    raise AssertionError("Retry policy exhausted without a result")


def invalid_response() -> OpenAIServiceError:
    return OpenAIServiceError(AIProblem("invalid_response", "invalid_response"))


def problem_from_record(message: str | None) -> AIProblem | None:
    """Read only our machine prefix, never display stored raw exception text."""
    match = re.match(r"^OpenAI \[([a-z_]+)/([A-Za-z0-9_.:-]{1,100})\]", message or "")
    return AIProblem(match[1], match[2]) if match else None
