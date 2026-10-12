"""Food_Porn administration: shared web login, SQLAdmin and Mini CRM."""

from __future__ import annotations

import hmac
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.crm.models import initialize_schema
from app.crm.router import router as crm_router
from app.crm.service import load_runtime_settings
from app.database.models import AppSetting, Customer, Menu, WallpaperOrder
from app.database.session import async_session_maker, engine
from src.billing.models import Account, Transaction
from src.orchestrator.models import ServiceInstance

settings = get_settings()
SESSION_SECRET = settings.admin_session_secret.get_secret_value() or secrets.token_urlsafe(48)


class AdminAuth(AuthenticationBackend):
    async def login(self, request) -> bool:
        values = await request.form()
        username, password = values.get("username"), values.get("password")
        configured = get_settings()
        expected_password = configured.admin_password.get_secret_value()
        if not expected_password or not isinstance(username, str) or not isinstance(password, str):
            return False
        if hmac.compare_digest(
            username.encode(), (configured.admin_username or "admin").encode()
        ) and hmac.compare_digest(password.encode(), expected_password.encode()):
            request.session.clear()
            request.session.update(admin_authenticated=True, crm_csrf=secrets.token_urlsafe(32))
            return True
        return False

    async def logout(self, request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request) -> bool:
        return request.session.get("admin_authenticated") is True


class CRMLink(BaseView):
    name = "Mini CRM · Обзор и управление"
    icon = "fa-solid fa-chart-line"

    @expose("/mini-crm", methods=["GET"])
    async def crm(self, request):
        return RedirectResponse("/crm")


class CustomerAdmin(ModelView, model=Customer):
    name = "Клиент"
    name_plural = "Клиенты"
    icon = "fa-solid fa-users"
    column_list = [
        Customer.id,
        Customer.name,
        Customer.telegram_user_id,
        Customer.phone,
        Customer.language,
        Customer.city,
    ]
    column_searchable_list = [Customer.name, Customer.phone]
    column_sortable_list = [Customer.created_at]
    can_create = can_edit = can_delete = False
    can_export = True


class MenuAdmin(ModelView, model=Menu):
    name = "Меню"
    name_plural = "Заказы меню"
    icon = "fa-solid fa-utensils"
    column_list = [
        Menu.id,
        Menu.customer_id,
        Menu.status,
        Menu.is_paid,
        Menu.price_amount,
        Menu.stars_amount,
        Menu.payment_system,
        Menu.created_at,
    ]
    column_sortable_list = [Menu.created_at, Menu.status]
    column_default_sort = ("created_at", True)
    can_create = can_edit = can_delete = False
    can_export = True


class GiftAdmin(ModelView, model=WallpaperOrder):
    name = "Подарок"
    name_plural = "Карты желаний"
    icon = "fa-solid fa-gift"
    column_list = [
        WallpaperOrder.id,
        WallpaperOrder.telegram_user_id,
        WallpaperOrder.amount,
        WallpaperOrder.stars_amount,
        WallpaperOrder.paid,
        WallpaperOrder.payment_system,
        WallpaperOrder.created_at,
    ]
    column_sortable_list = [WallpaperOrder.created_at]
    can_create = can_edit = can_delete = False
    can_export = True


class AccountAdmin(ModelView, model=Account):
    name = "Счёт"
    name_plural = "Ledger · Балансы"
    icon = "fa-solid fa-wallet"
    column_list = [Account.id, Account.owner_id, Account.available_balance, Account.held_balance]
    column_searchable_list = [Account.owner_id]
    can_create = can_edit = can_delete = False


class TransactionAdmin(ModelView, model=Transaction):
    name = "Транзакция"
    name_plural = "Ledger · Транзакции"
    icon = "fa-solid fa-receipt"
    column_list = [
        Transaction.id,
        Transaction.account_id,
        Transaction.type,
        Transaction.amount,
        Transaction.reference_id,
        Transaction.created_at,
    ]
    column_sortable_list = [Transaction.created_at]
    column_searchable_list = [Transaction.reference_id]
    can_create = can_edit = can_delete = False
    can_export = True


class AppSettingAdmin(ModelView, model=AppSetting):
    name = "Параметр"
    name_plural = "Параметры · просмотр"
    column_list = [AppSetting.key, AppSetting.value, AppSetting.description]
    can_create = can_edit = can_delete = False


class ServiceInstanceAdmin(ModelView, model=ServiceInstance):
    name_plural = "Сервисы"
    column_list = [
        ServiceInstance.id,
        ServiceInstance.name,
        ServiceInstance.service_type,
        ServiceInstance.status,
    ]
    can_create = can_edit = can_delete = False


@asynccontextmanager
async def application_lifespan(_app):
    await initialize_schema(engine)
    await load_runtime_settings(async_session_maker)
    yield


app = FastAPI(title="Food_Porn Mini CRM", version="3.1", lifespan=application_lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=settings.app_env == "production",
    max_age=8 * 3600,
)
app.include_router(crm_router)
auth_backend = AdminAuth(secret_key=SESSION_SECRET)
# The parent app owns the session, shared by /admin and /crm.
auth_backend.middlewares = []
admin = Admin(
    app=app, engine=engine, authentication_backend=auth_backend, title="Food_Porn · Administration"
)
for view in (
    CRMLink,
    CustomerAdmin,
    MenuAdmin,
    GiftAdmin,
    AccountAdmin,
    TransactionAdmin,
    AppSettingAdmin,
    ServiceInstanceAdmin,
):
    admin.add_view(view)


@app.get("/api/dashboard", include_in_schema=False)
async def dashboard_redirect():
    return RedirectResponse("/crm")


@app.middleware("http")
async def crm_response_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/crm") or request.url.path.startswith("/miniapp/api/admin"):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response
