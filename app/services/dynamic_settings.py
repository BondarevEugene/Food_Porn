# app/services/dynamic_settings.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import AppSetting
from app.config import get_settings


async def get_setting_value(db: AsyncSession, key: str, default: str = "") -> str:
    """
    Получает настройку из базы данных (AppSetting). Если её нет, возвращает значение из конфига или дефолт.
    """
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        return setting.value

    # Фолбек на системный конфиг
    settings = get_settings()
    return str(getattr(settings, key, default))


async def set_setting_value(db: AsyncSession, key: str, value: str, description: str = None) -> None:
    """
    Сохраняет или обновляет настройку в базе данных.
    """
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = value
        if description:
            setting.description = description
    else:
        setting = AppSetting(key=key, value=value, description=description)
        db.add(setting)

    await db.commit()
