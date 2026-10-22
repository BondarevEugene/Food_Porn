"""
==========================================================
FOOD_PORN • ADMIN SUITE
==========================================================
"""

from __future__ import annotations
import hmac

from fastapi import FastAPI, Request
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.ext.asyncio import create_async_engine

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.database.models import (
    Customer,
    Menu,
    MenuItem,
    GeneratedFile,
    AppSetting,
    ImageCache,
    WallpaperOrder,
    ShareLink,
    EmailDelivery,
    CurrencyRate,
    AIGenerationLog
)

settings = get_settings()

ADMIN_USER = getattr(settings, "admin_username", "") or "admin"
ADMIN_PASS = settings.admin_password.get_secret_value() if getattr(settings, "admin_password", None) else "admin"

db_url = settings.database_url
if db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)

class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form.get("username"), form.get("password")
        if (isinstance(username, str) and isinstance(password, str)
                and hmac.compare_digest(username, ADMIN_USER)
                and hmac.compare_digest(password, ADMIN_PASS)):
            request.session.update({"token": "admin_token"})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("token") == "admin_token"

app = FastAPI(title="FoodPorn Admin Panel")

# --- РЕГИСТРАЦИЯ ТОЛЬКО РЕАЛЬНЫХ ТАБЛИЦ ---

class CustomerAdmin(ModelView, model=Customer):
    name = "Клиент"
    name_plural = "👥 Клиенты"
    icon = "fa-solid fa-users"
    column_list = [Customer.id, Customer.name, Customer.telegram_user_id, Customer.phone, Customer.created_at]
    column_searchable_list = [Customer.name, Customer.phone, Customer.telegram_user_id]
    column_sortable_list = [Customer.created_at]

class MenuAdmin(ModelView, model=Menu):
    name = "Меню"
    name_plural = "📦 Заказы (Меню)"
    icon = "fa-solid fa-utensils"
    column_list = [Menu.id, Menu.customer_id, Menu.status, Menu.is_paid, Menu.created_at]
    column_searchable_list = [Menu.id, Menu.customer_id]

class MenuItemAdmin(ModelView, model=MenuItem):
    name = "Блюдо"
    name_plural = "🍕 Позиции меню"
    icon = "fa-solid fa-pizza-slice"
    column_list = [MenuItem.id, MenuItem.menu_id, MenuItem.category, MenuItem.title, MenuItem.generation_status]
    column_searchable_list = [MenuItem.title]

class GeneratedFileAdmin(ModelView, model=GeneratedFile):
    name = "Файл"
    name_plural = "📄 Сгенерированные PDF"
    icon = "fa-solid fa-file-pdf"
    column_list = [GeneratedFile.id, GeneratedFile.menu_id, GeneratedFile.kind, GeneratedFile.created_at]

class WallpaperOrderAdmin(ModelView, model=WallpaperOrder):
    name = "Заказ обоев"
    name_plural = "🖼️ Обои"
    icon = "fa-solid fa-image"
    column_list = [WallpaperOrder.id, WallpaperOrder.telegram_user_id, WallpaperOrder.amount, WallpaperOrder.paid]

class CurrencyRateAdmin(ModelView, model=CurrencyRate):
    name = "Курс валюты"
    name_plural = "💱 Курсы НБУ"
    icon = "fa-solid fa-money-bill-trend-up"
    column_list = [CurrencyRate.date, CurrencyRate.currency_from, CurrencyRate.currency_to, CurrencyRate.rate]

class AIGenerationLogAdmin(ModelView, model=AIGenerationLog):
    name = "Лог ИИ"
    name_plural = "🤖 Расходы на ИИ"
    icon = "fa-solid fa-microchip"
    column_list = [AIGenerationLog.id, AIGenerationLog.user_id, AIGenerationLog.model_name, AIGenerationLog.cost_usd, AIGenerationLog.cost_uah, AIGenerationLog.created_at]
    column_sortable_list = [AIGenerationLog.created_at]

class AppSettingAdmin(ModelView, model=AppSetting):
    name = "Настройка"
    name_plural = "⚙️ Настройки"
    icon = "fa-solid fa-sliders"
    column_list = [AppSetting.key, AppSetting.value]


# Подключаем админку
admin = Admin(
    app=app,
    engine=engine,
    authentication_backend=AdminAuth(secret_key="food_porn_secure_secret"),
    title="FoodPorn Control",
)

admin.add_view(CustomerAdmin)
admin.add_view(MenuAdmin)
admin.add_view(MenuItemAdmin)
admin.add_view(GeneratedFileAdmin)
admin.add_view(WallpaperOrderAdmin)
admin.add_view(CurrencyRateAdmin)
admin.add_view(AIGenerationLogAdmin)
admin.add_view(AppSettingAdmin)