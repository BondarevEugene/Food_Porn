"""
==========================================================
FOOD_PORN • ENTERPRISE CRM & ADMINISTRATION SUITE
==========================================================
"""

from __future__ import annotations

import hmac
from decimal import Decimal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import get_settings

from app.database.models import AppSetting, Customer, Menu, CurrencyRate, AIGenerationLog
from src.billing.models import Account, Transaction
from src.orchestrator.models import ServiceInstance
from app.services.cost_tracker import get_monthly_ai_costs

settings = get_settings()

ADMIN_USER = getattr(settings, "admin_username", "") or "admin"
ADMIN_PASS = settings.admin_password.get_secret_value() if settings.admin_password.get_secret_value() else "admin"

db_url = settings.database_url
if db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)


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
    body { background-color: var(--bs-body-bg) !important; color: var(--bs-body-color) !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    .sidebar { background: #0f172a !important; border-right: 1px solid #1e293b !important; }
    .sidebar .nav-link { color: #94a3b8 !important; border-radius: 8px; margin: 4px 12px; transition: all 0.2s; }
    .sidebar .nav-link:hover, .sidebar .nav-link.active { background: rgba(212, 175, 55, 0.15) !important; color: #d4af37 !important; }
    .navbar { background: #0f172a !important; border-bottom: 1px solid #1e293b !important; }
    .card { background: #131c31 !important; border: 1px solid #1e293b !important; border-radius: 12px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4); }
    .table { color: #f8fafc !important; width: 100% !important; table-layout: auto !important; }
    .table th, .table td { white-space: nowrap !important; overflow: hidden; text-overflow: ellipsis; max-width: 250px; vertical-align: middle !important; }
    .table-striped > tbody > tr:nth-of-type(odd) > * { background-color: rgba(255, 255, 255, 0.015) !important; color: #f8fafc !important; }
    .btn-primary { background-color: #d4af37 !important; border-color: #d4af37 !important; color: #0b0f19 !important; font-weight: 600; border-radius: 8px; }
    .btn-primary:hover { background-color: #c5a028 !important; border-color: #c5a028 !important; color: #000 !important; }
    .form-control, .form-select { background-color: #1e293b !important; border-color: #334155 !important; color: #fff !important; border-radius: 8px; }
    .form-control:focus { background-color: #1e293b !important; border-color: #d4af37 !important; color: #fff !important; box-shadow: 0 0 0 0.25rem rgba(212, 175, 55, 0.25); }
    .dropdown-menu { background-color: #0f172a; border: 1px solid #1e293b; }
    .dropdown-item { color: #cbd5e1; }
    .dropdown-item:hover { background-color: rgba(212, 175, 55, 0.15); color: #d4af37; }
</style>
"""


class CustomerAdmin(ModelView, model=Customer):
    name = "Клиент"
    name_plural = "👥 База Лидов и Клиентов"
    icon = "fa-solid fa-users-line"
    column_list = [Customer.id, Customer.name, Customer.telegram_user_id, Customer.phone, Customer.created_at]
    column_searchable_list = [Customer.name, Customer.phone, Customer.telegram_user_id]
    column_sortable_list = [Customer.created_at]


class MenuAdmin(ModelView, model=Menu):
    name = "Заказ меню"
    name_plural = "📦 Воронка Заказов (Menu Pipeline)"
    icon = "fa-solid fa-utensils"
    column_list = [Menu.id, Menu.customer_id, Menu.status, Menu.created_at]
    column_searchable_list = [Menu.id, Menu.customer_id]
    column_sortable_list = [Menu.status, Menu.created_at]


class AccountAdmin(ModelView, model=Account):
    name = "Счет"
    name_plural = "💳 Финансовые Счета"
    icon = "fa-solid fa-wallet"
    column_list = [Account.id, Account.owner_id, Account.available_balance, Account.held_balance]


class TransactionAdmin(ModelView, model=Transaction):
    name = "Транзакция"
    name_plural = "🧾 История Платежей (Portmone)"
    icon = "fa-solid fa-receipt"
    column_list = [Transaction.id, Transaction.account_id, Transaction.type, Transaction.amount, Transaction.reference_id, Transaction.created_at]
    column_sortable_list = [Transaction.created_at]


class ServiceInstanceAdmin(ModelView, model=ServiceInstance):
    name = "Микросервис"
    name_plural = "⚙️ Оркестратор Ботов (OmniFactory)"
    icon = "fa-solid fa-server"
    column_list = [ServiceInstance.id, ServiceInstance.name, ServiceInstance.service_type, ServiceInstance.status]


class CurrencyRateAdmin(ModelView, model=CurrencyRate):
    name = "Курс валют"
    name_plural = "💱 История Курсов Валют (USD/UAH)"
    icon = "fa-solid fa-money-bill-trend-up"
    column_list = [CurrencyRate.date, CurrencyRate.currency_from, CurrencyRate.currency_to, CurrencyRate.rate, CurrencyRate.created_at]
    column_sortable_list = [CurrencyRate.date]


class AIGenerationLogAdmin(ModelView, model=AIGenerationLog):
    name = "Лог ИИ"
    name_plural = "🤖 Себестоимость ИИ (Token Ledger)"
    icon = "fa-solid fa-microchip"
    column_list = [AIGenerationLog.id, AIGenerationLog.user_id, AIGenerationLog.model_name, AIGenerationLog.prompt_tokens, AIGenerationLog.completion_tokens, AIGenerationLog.cost_usd, AIGenerationLog.exchange_rate, AIGenerationLog.cost_uah, AIGenerationLog.created_at]
    column_sortable_list = [AIGenerationLog.created_at]
    column_searchable_list = [AIGenerationLog.model_name]


class AppSettingAdmin(ModelView, model=AppSetting):
    name = "Параметр"
    name_plural = "🔧 Управление Конфигом (Config Hub)"
    icon = "fa-solid fa-sliders"
    column_list = [AppSetting.key, AppSetting.value, AppSetting.description]


app = FastAPI(title="FoodPorn Enterprise CRM & AI Ledger", version="3.3")
engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


@app.on_event("startup")
async def startup_database_preparation():
    from app.database.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


admin = Admin(
    app=app,
    engine=engine,
    authentication_backend=AdminAuth(secret_key="food_porn_enterprise_secure_secret_key"),
    title="FoodPorn • Control Center",
    logo_url="https://img.icons8.com/color/48/restaurant.png"
)

admin.add_view(CustomerAdmin)
admin.add_view(MenuAdmin)
admin.add_view(AccountAdmin)
admin.add_view(TransactionAdmin)
admin.add_view(ServiceInstanceAdmin)
admin.add_view(CurrencyRateAdmin)
admin.add_view(AIGenerationLogAdmin)
admin.add_view(AppSettingAdmin)


@app.get("/api/dashboard", response_class=HTMLResponse)
async def get_dashboard_metrics(request: Request):
    if not request.session.get("token") == "admin_enterprise_token":
        raise HTTPException(status_code=403, detail="Требуется авторизация администратора")

    try:
        async with engine.connect() as conn:
            leads = await conn.scalar(text("SELECT COUNT(*) FROM customers")) or 0
            paid = await conn.scalar(text("SELECT COUNT(*) FROM menus WHERE status = 'PAID' OR status != 'draft'")) or 0
            total_revenue_cents = await conn.scalar(text("SELECT SUM(amount) FROM transactions WHERE type = 'deposit'")) or 0
    except Exception:
        leads, paid, total_revenue_cents = 0, 0, 0

    conversion = (paid / leads * 100) if leads > 0 else 0
    revenue_uah = total_revenue_cents / 100

    # Получаем агрегированную статистику по ИИ за месяц
    async with async_session_maker() as session:
        ai_stats = await get_monthly_ai_costs(session)

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>FoodPorn • Enterprise Analytics Hub</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        {CUSTOM_ADMIN_CSS}
    </head>
    <body class="p-4">
        <div class="container my-4">
            <div class="d-flex justify-content-between align-items-center mb-5 pb-3 border-bottom border-secondary">
                <div>
                    <h1 class="h3 fw-bold text-warning mb-1"><i class="fa-solid fa-crown me-2"></i> FoodPorn Ecosystem Hub</h1>
                    <p class="text-muted m-0">Управление экосистемой, финансами и себестоимостью ИИ • OmniFactory Enterprise</p>
                </div>
                <div class="d-flex gap-3">
                    <a href="/admin" class="btn btn-primary px-4 shadow-sm"><i class="fa-solid fa-table-list me-2"></i> Таблицы CRM</a>
                </div>
            </div>

            <!-- Основные метрики -->
            <div class="row g-4 mb-4">
                <div class="col-md-3">
                    <div class="card p-4 h-100 border-start border-warning border-4">
                        <h6 class="text-muted text-uppercase fs-7 mb-2">Всего лидов</h6>
                        <h2 class="fw-bold mb-0 text-light">{leads}</h2>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card p-4 h-100 border-start border-success border-4">
                        <h6 class="text-muted text-uppercase fs-7 mb-2">Оплаченные заказы</h6>
                        <h2 class="fw-bold mb-0 text-success">{paid}</h2>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card p-4 h-100 border-start border-info border-4">
                        <h6 class="text-muted text-uppercase fs-7 mb-2">Конверсия воронки</h6>
                        <h2 class="fw-bold mb-0 text-info">{conversion:.1f}%</h2>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card p-4 h-100 border-start border-primary border-4">
                        <h6 class="text-muted text-uppercase fs-7 mb-2">Общая выручка</h6>
                        <h2 class="fw-bold mb-0 text-warning">{revenue_uah:,.2f} UAH</h2>
                    </div>
                </div>
            </div>

            <!-- AI Cost Analytics блок -->
            <div class="row g-4 mb-5">
                <div class="col-md-12">
                    <div class="card p-4 border-start border-danger border-4">
                        <h5 class="text-warning mb-3"><i class="fa-solid fa-microchip me-2"></i> Себестоимость ИИ за текущий месяц (AI Token Ledger)</h5>
                        <div class="row g-3">
                            <div class="col-md-3">
                                <p class="text-muted mb-1">Всего генераций</p>
                                <h4 class="text-light">{ai_stats["total_generations"]}</h4>
                            </div>
                            <div class="col-md-3">
                                <p class="text-muted mb-1">Расходы на ИИ ($ USD)</p>
                                <h4 class="text-danger">${ai_stats["total_cost_usd"]:,.4f}</h4>
                            </div>
                            <div class="col-md-3">
                                <p class="text-muted mb-1">Расходы на ИИ (₴ UAH по курсу)</p>
                                <h4 class="text-warning">₴{ai_stats["total_cost_uah"]:,.2f}</h4>
                            </div>
                            <div class="col-md-3">
                                <p class="text-muted mb-1">Средняя цена 1 запроса</p>
                                <h4 class="text-info">₴{ai_stats["avg_cost_uah"]:,.4f}</h4>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <footer class="text-center text-muted pt-4 mt-5 border-top border-secondary fs-7">
                <p class="mb-1">FoodPorn &bull; Old Money Architecture &bull; Built with precision &amp; passion for excellence 💛</p>
                <small class="text-secondary">OmniFactory Backend Supervisor &copy; 2026</small>
            </footer>
        </div>
    </body>
    </html>
    """
