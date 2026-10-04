"""
==========================================================
FOOD_PORN • ENTERPRISE CRM & ADMINISTRATION SUITE
==========================================================
"""

import hmac
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import sys
from pathlib import Path
# Добавляем корень проекта в путь поиска модулей, чтобы config импортировался без ошибок
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import get_settings

from app.database.models import AppSetting, Customer, Menu
from src.billing.models import Account, Transaction
from src.orchestrator.models import ServiceInstance

settings = get_settings()

ADMIN_USER = getattr(settings, "admin_username", "") or "admin"
ADMIN_PASS = settings.admin_password.get_secret_value() if settings.admin_password.get_secret_value() else "admin"


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form.get("username"), form.get("password")
        if (isinstance(username, str) and isinstance(password, str)
                and hmac.compare_digest(username, ADMIN_USER)
                and hmac.compare_digest(password, ADMIN_PASS)):
            request.session.update({"token": "admin_enterprise_token"})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("token") == "admin_enterprise_token"


CUSTOM_ADMIN_CSS = """
<style>
    :root {
        --bs-primary: #d4af37;
        --bs-primary-rgb: 212, 175, 55;
        --bs-body-bg: #0b0f19;
        --bs-body-color: #e2e8f0;
    }
    body { background-color: var(--bs-body-bg) !important; color: var(--bs-body-color) !important; }
    .sidebar { background: #0f172a !important; border-right: 1px solid #1e293b !important; }
    .navbar { background: #0f172a !important; border-bottom: 1px solid #1e293b !important; }
    .card { background: #131c31 !important; border: 1px solid #1e293b !important; border-radius: 12px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); }
    .table { color: #f8fafc !important; }
    .table-striped > tbody > tr:nth-of-type(odd) > * { background-color: rgba(255, 255, 255, 0.02) !important; color: #f8fafc !important; }
    .btn-primary { background-color: #d4af37 !important; border-color: #d4af37 !important; color: #000 !important; font-weight: 600; }
    .btn-primary:hover { background-color: #c5a028 !important; border-color: #c5a028 !important; }
    .form-control, .form-select { background-color: #1e293b !important; border-color: #334155 !important; color: #fff !important; }
    .form-control:focus { background-color: #1e293b !important; border-color: #d4af37 !important; color: #fff !important; box-shadow: 0 0 0 0.25rem rgba(212, 175, 55, 0.25); }
</style>
"""


# --- ПРЕДСТАВЛЕНИЯ АДМИНКИ ---
class CustomerAdmin(ModelView, model=Customer):
    name = "👥 Клиент (Лид)"
    name_plural = "👥 Клиенты (LTV & Лиды)"
    icon = "fa-solid fa-users"
    column_list = [Customer.id, Customer.name, Customer.telegram_user_id, Customer.phone, Customer.created_at]
    column_searchable_list = [Customer.name, Customer.phone, Customer.telegram_user_id]
    column_sortable_list = [Customer.created_at]
    column_details_list = "__all__"
    can_export = True


class MenuAdmin(ModelView, model=Menu):
    name = "📦 Заказ (Меню)"
    name_plural = "📦 Воронка Заказов"
    icon = "fa-solid fa-layer-group"
    column_list = [Menu.id, Menu.customer_id, Menu.status, Menu.created_at]
    column_searchable_list = [Menu.id, Menu.customer_id]
    column_sortable_list = [Menu.status, Menu.created_at]
    column_default_sort = ("created_at", True)


class AccountAdmin(ModelView, model=Account):
    name = "💳 Баланс пользователя"
    name_plural = "💳 Финансы (Балансы счетов)"
    icon = "fa-solid fa-wallet"
    column_list = [Account.id, Account.owner_id, Account.available_balance, Account.held_balance]
    column_searchable_list = [Account.owner_id]
    can_create = True
    can_edit = True
    can_delete = False


class TransactionAdmin(ModelView, model=Transaction):
    name = "🧾 Транзакция"
    name_plural = "🧾 История платежей (Portmone Ledger)"
    icon = "fa-solid fa-money-bill-transfer"
    column_list = [Transaction.id, Transaction.account_id, Transaction.type, Transaction.amount, Transaction.reference_id, Transaction.created_at]
    column_sortable_list = [Transaction.created_at]
    column_searchable_list = [Transaction.reference_id]
    can_create = False
    can_edit = False
    can_delete = False
    can_export = True


class ServiceInstanceAdmin(ModelView, model=ServiceInstance):
    name = "⚙️ Микросервис"
    name_plural = "⚙️ Управление ботами (OmniFactory)"
    icon = "fa-solid fa-server"
    column_list = [ServiceInstance.id, ServiceInstance.name, ServiceInstance.service_type, ServiceInstance.status]


class AppSettingAdmin(ModelView, model=AppSetting):
    name = "🔧 Параметр конфигурации"
    name_plural = "🔧 Управление конфигом и ценами (Config Hub)"
    icon = "fa-solid fa-sliders"
    column_list = [AppSetting.key, AppSetting.value, AppSetting.description]
    column_searchable_list = [AppSetting.key, AppSetting.description]
    column_sortable_list = [AppSetting.key]
    form_widget_args = {"value": {"rows": 6}}


app = FastAPI(title="FoodPorn Enterprise CRM", version="3.0")
engine = create_async_engine(settings.database_url, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


@app.on_event("startup")
async def seed_default_settings():
    """
    Автоматически переносит все ключевые параметры из config.py в базу данных при старте,
    позволяя администратору управлять ими из веб-интерфейса.
    """
    async with async_session_maker() as session:
        default_configs = {
            "usd_exchange_rate": (str(settings.usd_exchange_rate), "Курс USD к UAH для расчетов"),
            "price_electronic_uah": (str(settings.price_electronic_uah), "Цена электронной версии в UAH"),
            "price_print_uah": (str(settings.price_print_uah), "Цена печатной версии с доставкой в UAH"),
            "price_electronic_usd": (str(settings.price_electronic_usd), "Цена электронной версии в USD"),
            "price_print_usd": (str(settings.price_print_usd), "Цена печатной версии в USD"),
            "menu_price_stars": (str(settings.menu_price_stars), "Стоимость генерации в Telegram Stars"),
            "gift_price_stars": (str(settings.gift_price_stars), "Стоимость подарка в Telegram Stars"),
            "printshop_name": (str(settings.printshop_name), "Название партнерской типографии"),
            "printshop_email": (str(settings.printshop_email), "Email типографии для отправки макетов заказов"),
            "portmone_payee_id": (str(settings.portmone_payee_id), "Идентификатор плательщика (Payee ID) в Portmone"),
            "use_mock_images": (str(settings.use_mock_images), "Использовать мок-изображения (true/false)"),
        }

        for key, (val, desc) in default_configs.items():
            existing = await session.scalar(select(AppSetting).where(AppSetting.key == key))
            if not existing:
                session.add(AppSetting(key=key, value=val, description=desc))
        await session.commit()


admin = Admin(
    app=app,
    engine=engine,
    authentication_backend=AdminAuth(secret_key="food_porn_enterprise_secure_secret_key"),
    title="FoodPorn Enterprise Suite",
    logo_url="https://img.icons8.com/color/48/000000/fine-dining.png"
)

# Регистрируем абсолютно все представления в админке
admin.add_view(CustomerAdmin)
admin.add_view(MenuAdmin)
admin.add_view(AccountAdmin)
admin.add_view(TransactionAdmin)
admin.add_view(ServiceInstanceAdmin)
admin.add_view(AppSettingAdmin)


# --- ПРЕМИАЛЬНЫЙ ДАШБОРД МЕТРИК И АНАЛИТИКИ ---
@app.get("/api/dashboard", response_class=HTMLResponse)
async def get_dashboard_metrics(request: Request):
    if not request.session.get("token") == "admin_enterprise_token":
        raise HTTPException(status_code=403, detail="Administrator login required")

    async with engine.connect() as conn:
        leads = await conn.scalar(text("SELECT COUNT(*) FROM customers")) or 0
        drafts = await conn.scalar(text("SELECT COUNT(*) FROM menus WHERE status = 'draft'")) or 0
        paid = await conn.scalar(text("SELECT COUNT(*) FROM menus WHERE status = 'PAID' OR status != 'draft'")) or 0
        total_revenue_cents = await conn.scalar(text("SELECT SUM(amount) FROM transactions WHERE type = 'deposit'")) or 0

    conversion = (paid / leads * 100) if leads > 0 else 0
    revenue_uah = total_revenue_cents / 100

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>FoodPorn Enterprise Analytics</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/css/min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        {CUSTOM_ADMIN_CSS}
    </head>
    <body class="p-5">
        <div class="container">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h2><i class="fa-solid fa-chart-line text-warning"></i> FoodPorn Enterprise Analytics</h2>
                <a href="/admin" class="btn btn-primary"><i class="fa-solid fa-arrow-left"></i> Вернуться в админку</a>
            </div>
            <div class="row g-4">
                <div class="col-md-3">
                    <div class="card p-4 text-center">
                        <h6 class="text-muted">Всего лидов</h6>
                        <h3>{leads}</h3>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card p-4 text-center">
                        <h6 class="text-muted">Успешных оплат</h6>
                        <h3 class="text-success">{paid}</h3>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card p-4 text-center">
                        <h6 class="text-muted">Конверсия воронки</h6>
                        <h3 class="text-warning">{conversion:.1f}%</h3>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card p-4 text-center">
                        <h6 class="text-muted">Выручка</h6>
                        <h3 class="text-info">{revenue_uah:.2f} UAH</h3>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
