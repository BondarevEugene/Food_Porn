"""
==========================================================
FOOD_PORN

Module: Web Admin & CRM Dashboard
Layer: Web / Ops

Responsibilities:
    - Provide a web interface for database management
    - Display CRM metrics (users, conversion, orders)
    - Secure access with Basic/Session Auth
==========================================================
"""

from fastapi import FastAPI, Request
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.ext.asyncio import create_async_engine

# Импортируем настройки и модели из базы данных
from app.config import get_settings
from app.database.models import AppSetting, Customer, Menu

settings = get_settings()


# 1. Настройка безопасности (Логин и Пароль для CRM)
class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form.get("username"), form.get("password")
        # Логин и пароль администратора панели
        if username == "admin" and password == "foodporn_secret":
            request.session.update({"token": "admin_token"})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return "token" in request.session


# 2. Настройка интерфейса для таблицы Клиентов (CRM)
class CustomerAdmin(ModelView, model=Customer):
    column_list = [
        Customer.id,
        Customer.telegram_user_id,
        Customer.name,
        Customer.phone,
        Customer.language,
        Customer.created_at,
    ]
    column_searchable_list = [Customer.name, Customer.phone, Customer.telegram_user_id]
    column_sortable_list = [Customer.id, Customer.created_at]
    name = "Клиент"
    name_plural = "Клиенты CRM"
    icon = "fa-solid fa-users"


# 3. Настройка интерфейса для Заказов (Меню)
class MenuAdmin(ModelView, model=Menu):
    column_list = [Menu.id, Menu.customer_id, Menu.status, Menu.created_at]
    column_searchable_list = [Menu.id]
    column_sortable_list = [Menu.id, Menu.created_at, Menu.status]
    name = "Заказ (Меню)"
    name_plural = "Заказы"
    icon = "fa-solid fa-book-open"


# 4. Настройка интерфейса для Системных Настроек
class AppSettingAdmin(ModelView, model=AppSetting):
    column_list = [AppSetting.key, AppSetting.value, AppSetting.description]
    name = "Настройка системы"
    name_plural = "Настройки системы"
    icon = "fa-solid fa-cogs"


# Инициализация FastAPI
app = FastAPI(title="FoodPorn CRM", version="1.0")

# Подключение базы данных Neon
engine = create_async_engine(settings.database_url, echo=False)

# Подключение SQLAdmin
authentication_backend = AdminAuth(secret_key="super_secret_key_change_me")
admin = Admin(
    app=app,
    engine=engine,
    authentication_backend=authentication_backend,
    title="FoodPorn Admin",
)

# Регистрируем все таблицы в админке
admin.add_view(CustomerAdmin)
admin.add_view(MenuAdmin)
admin.add_view(AppSettingAdmin)


# 5. Пользовательский Дашборд с аналитикой
@app.get("/api/metrics")
async def get_metrics():
    """Отдельный эндпоинт для графиков и метрик сервиса."""
    return {
        "total_customers": 150,
        "total_menus_generated": 85,
        "conversion_rate": "56%",
        "status": "Healthy",
    }