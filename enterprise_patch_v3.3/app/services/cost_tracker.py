"""
==========================================================
FOOD_PORN • AI COST & CURRENCY EXCHANGE TRACKER SERVICE
==========================================================
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import aiohttp
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import CurrencyRate, AIGenerationLog


async def get_or_fetch_exchange_rate(session: AsyncSession) -> Decimal:
    """
    Получает курс USD к UAH на сегодня.
    Сначала проверяет локальную базу (история курсов за день).
    Если на сегодня курса нет, делает запрос к публичному API НБУ или резервному источнику,
    сохраняет в таблицу currency_rates и возвращает.
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # 1. Проверяем локальный кэш / историю
    stmt = select(CurrencyRate).where(CurrencyRate.date == today_str)
    result = await session.execute(stmt)
    rate_record = result.scalar_one_or_none()
    
    if rate_record:
        return rate_record.rate
        
    # 2. Если за сегодня курса нет, запрашиваем из API НБУ (или ставим дефолт при оффлайне)
    rate_val = Decimal("41.2500") # дефолтный резервный курс
    try:
        url = f"https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&date={datetime.now(timezone.utc).strftime('%Y%m%d')}&json"
        async with aiohttp.ClientSession() as client:
            async with client.get(url, timeout=5.0) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list):
                        rate_val = Decimal(str(data[0].get("rate", 41.25)))
    except Exception:
        # При отсутствии сети берем последний известный курс из базы
        last_stmt = select(CurrencyRate).order_by(CurrencyRate.date.desc()).limit(1)
        last_res = await session.execute(last_stmt)
        last_rec = last_res.scalar_one_or_none()
        if last_rec:
            rate_val = last_rec.rate

    # 3. Сохраняем в историю курсов
    new_rate = CurrencyRate(date=today_str, currency_from="USD", currency_to="UAH", rate=rate_val)
    session.add(new_rate)
    await session.commit()
    
    return rate_val


async def log_ai_generation(
    session: AsyncSession,
    user_id: int,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal
) -> AIGenerationLog:
    """
    Логирует каждую генерацию ИИ с автоматическим пересчетом в UAH по актуальному курсу дня.
    """
    rate = await get_or_fetch_exchange_rate(session)
    cost_uah = cost_usd * rate
    
    log_entry = AIGenerationLog(
        user_id=user_id,
        model_name=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        exchange_rate=rate,
        cost_uah=cost_uah
    )
    session.add(log_entry)
    await session.commit()
    await session.refresh(log_entry)
    return log_entry


async def get_monthly_ai_costs(session: AsyncSession) -> dict:
    """
    Считает агрегированную себестоимость за текущий месяц (USD и UAH),
    а также среднюю стоимость одной генерации.
    """
    current_month_prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    
    stmt = select(
        func.count(AIGenerationLog.id),
        func.sum(AIGenerationLog.prompt_tokens),
        func.sum(AIGenerationLog.completion_tokens),
        func.sum(AIGenerationLog.cost_usd),
        func.sum(AIGenerationLog.cost_uah)
    ).where(func.to_char(AIGenerationLog.created_at, 'YYYY-MM') == current_month_prefix)
    
    res = await session.execute(stmt)
    row = res.one_or_none()
    
    if not row or row[0] == 0:
        return {
            "total_generations": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_cost_usd": Decimal("0.00"),
            "total_cost_uah": Decimal("0.00"),
            "avg_cost_usd": Decimal("0.00"),
            "avg_cost_uah": Decimal("0.00"),
        }
        
    count, p_tokens, c_tokens, usd_sum, uah_sum = row
    count = count or 1
    
    return {
        "total_generations": count,
        "total_prompt_tokens": p_tokens or 0,
        "total_completion_tokens": c_tokens or 0,
        "total_cost_usd": usd_sum or Decimal("0.00"),
        "total_cost_uah": uah_sum or Decimal("0.00"),
        "avg_cost_usd": (usd_sum or Decimal("0.00")) / count,
        "avg_cost_uah": (uah_sum or Decimal("0.00")) / count,
    }
