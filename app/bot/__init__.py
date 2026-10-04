"""
==========================================================
FOOD_PORN & OLD MONEY MANIFESTATIONS
Module: Bot Routers Registry
==========================================================
"""

from aiogram import Dispatcher

from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.registration import router as registration_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.wallpaper import router as wallpaper_router


def setup_routers(dp: Dispatcher) -> None:
    """Реєструє всі роутери додатку в головному диспетчері."""
    dp.include_router(admin_router)
    dp.include_router(start_router)
    dp.include_router(wallpaper_router)
    dp.include_router(registration_router)