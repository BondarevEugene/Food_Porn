"""
==========================================================
FOOD_PORN

Module: Settings Management Service
Layer: Services
==========================================================
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AppSetting


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    result = await session.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalars().first()
    return setting.value if setting else default

async def set_setting(session: AsyncSession, key: str, value: str, description: str | None = None) -> None:
    result = await session.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalars().first()
    if setting:
        setting.value = value
        if description:
            setting.description = description
    else:
        setting = AppSetting(key=key, value=value, description=description)
        session.add(setting)
    await session.commit()

async def get_vip_users(session: AsyncSession, default_users: list[str] | None = None) -> list[str]:
    defaults = default_users if default_users is not None else ["Voloshka0602", "MenuDishesForLove", "bondarev_e"]
    val = await get_setting(session, "vip_usernames", ",".join(defaults))
    return [u.strip() for u in val.split(",") if u.strip()]

async def get_collage_price(session: AsyncSession) -> int:
    val = await get_setting(session, "collage_price_uah", "500")
    try:
        return int(val)
    except ValueError:
        return 500
