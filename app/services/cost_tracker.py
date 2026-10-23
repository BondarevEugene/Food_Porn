"""
==========================================================
FOOD_PORN

Module: AI Cost and Currency Tracker
Layer: Service

Responsibilities:
    - Persist one auditable row for every successful AI operation
    - Attribute estimated cost to a user, product and order
    - Convert provider USD cost to UAH using a daily NBU rate
    - Aggregate any explicit UTC period without PostgreSQL-only SQL
==========================================================
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import aiohttp
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AIGenerationLog, CurrencyRate

logger = logging.getLogger(__name__)
MILLION = Decimal(1_000_000)


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def response_usage(response: Any) -> dict[str, int]:
    """Read token usage from chat and image SDK responses defensively."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"input": 0, "output": 0, "cached": 0, "image_input": 0, "image_output": 0}
    input_tokens = _integer(getattr(usage, "prompt_tokens", None)) or _integer(
        getattr(usage, "input_tokens", None)
    )
    output_tokens = _integer(getattr(usage, "completion_tokens", None)) or _integer(
        getattr(usage, "output_tokens", None)
    )
    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    cached = _integer(getattr(input_details, "cached_tokens", None))
    image_input = _integer(getattr(input_details, "image_tokens", None))
    image_output = _integer(getattr(output_details, "image_tokens", None))
    return {
        "input": input_tokens,
        "output": output_tokens,
        "cached": cached,
        "image_input": image_input,
        "image_output": image_output,
    }


def estimate_text_cost(response: Any, settings: Settings) -> Decimal:
    """Estimate a text call; actual organization billing is imported separately."""
    usage = response_usage(response)
    cached = min(usage["cached"], usage["input"])
    uncached = usage["input"] - cached
    return (
        Decimal(uncached) * settings.openai_text_input_usd_per_million
        + Decimal(cached) * settings.openai_cached_input_usd_per_million
        + Decimal(usage["output"]) * settings.openai_text_output_usd_per_million
    ) / MILLION


async def get_or_fetch_exchange_rate(session: AsyncSession) -> Decimal:
    """Return today's USD/UAH rate, preferring the cached NBU value."""
    now = datetime.now(UTC)
    today = now.strftime("%Y-%m-%d")
    existing = await session.scalar(select(CurrencyRate).where(CurrencyRate.date == today))
    if existing:
        return Decimal(existing.rate)

    rate = Decimal("41.2500")
    try:
        url = (
            "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
            f"?valcode=USD&date={now.strftime('%Y%m%d')}&json"
        )
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as client:
            async with client.get(url) as response:
                if response.status == 200:
                    payload = await response.json()
                    if isinstance(payload, list) and payload:
                        rate = Decimal(str(payload[0]["rate"]))
    except Exception as exc:
        logger.warning("NBU exchange rate is unavailable: %s", type(exc).__name__)
        previous = await session.scalar(select(CurrencyRate).order_by(CurrencyRate.date.desc()))
        if previous:
            rate = Decimal(previous.rate)

    session.add(CurrencyRate(date=today, currency_from="USD", currency_to="UAH", rate=rate))
    await session.commit()
    return rate


async def log_ai_generation(
    session: AsyncSession,
    user_id: int,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal,
    *,
    operation: str = "unknown",
    product_type: str | None = None,
    order_id: str | int | None = None,
    request_id: str | None = None,
    cached_input_tokens: int = 0,
    pricing_source: str = "estimate",
    details: dict[str, Any] | None = None,
) -> AIGenerationLog:
    """Write an AI ledger row. This function never receives or stores API secrets."""
    rate = await get_or_fetch_exchange_rate(session)
    normalized_cost = max(Decimal(0), Decimal(cost_usd))
    entry = AIGenerationLog(
        user_id=user_id,
        provider="openai",
        model_name=model_name,
        operation=operation,
        product_type=product_type,
        order_id=str(order_id) if order_id is not None else None,
        request_id=request_id,
        prompt_tokens=_integer(prompt_tokens),
        completion_tokens=_integer(completion_tokens),
        cached_input_tokens=_integer(cached_input_tokens),
        cost_usd=normalized_cost,
        exchange_rate=rate,
        cost_uah=normalized_cost * rate,
        status="success",
        pricing_source=pricing_source,
        details=details,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def log_openai_response(
    session: AsyncSession,
    *,
    settings: Settings,
    response: Any,
    user_id: int,
    model_name: str,
    operation: str,
    product_type: str | None = None,
    order_id: str | int | None = None,
    cost_usd: Decimal | None = None,
    details: dict[str, Any] | None = None,
) -> AIGenerationLog:
    usage = response_usage(response)
    return await log_ai_generation(
        session,
        user_id,
        model_name,
        usage["input"],
        usage["output"],
        estimate_text_cost(response, settings) if cost_usd is None else cost_usd,
        operation=operation,
        product_type=product_type,
        order_id=order_id,
        request_id=getattr(response, "_request_id", None),
        cached_input_tokens=usage["cached"],
        pricing_source="usage_estimate" if usage["input"] or usage["output"] else "fallback_estimate",
        details={
            **(details or {}),
            "image_input_tokens": usage["image_input"],
            "image_output_tokens": usage["image_output"],
        },
    )


async def get_ai_costs(
    session: AsyncSession, begin: datetime, end: datetime
) -> dict[str, Decimal | int]:
    row = (
        await session.execute(
            select(
                func.count(AIGenerationLog.id),
                func.sum(AIGenerationLog.prompt_tokens),
                func.sum(AIGenerationLog.completion_tokens),
                func.sum(AIGenerationLog.cost_usd),
                func.sum(AIGenerationLog.cost_uah),
            ).where(AIGenerationLog.created_at >= begin, AIGenerationLog.created_at <= end)
        )
    ).one()
    count, input_tokens, output_tokens, usd, uah = row
    return {
        "total_generations": int(count or 0),
        "total_prompt_tokens": int(input_tokens or 0),
        "total_completion_tokens": int(output_tokens or 0),
        "total_cost_usd": Decimal(usd or 0),
        "total_cost_uah": Decimal(uah or 0),
    }


async def get_monthly_ai_costs(session: AsyncSession) -> dict:
    now = datetime.now(UTC)
    begin = datetime(now.year, now.month, 1, tzinfo=UTC)
    totals = await get_ai_costs(session, begin, now)
    count = int(totals["total_generations"])
    totals["avg_cost_usd"] = Decimal(totals["total_cost_usd"]) / max(count, 1)
    totals["avg_cost_uah"] = Decimal(totals["total_cost_uah"]) / max(count, 1)
    return totals
