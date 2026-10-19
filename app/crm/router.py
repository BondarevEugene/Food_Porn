"""Authenticated CRM API and a public shell containing no customer data."""

from __future__ import annotations

import re
import secrets
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.crm import integrations, service
from app.crm.models import Audit, CustomerNote, Expense, Integration
from app.crm.security import crm_identity, decrypt_credentials, encrypt_credentials, require_owner
from app.database.models import AppSetting, Customer, WallpaperOrder
from app.database.session import async_session_maker
from app.services.payment import PaymentService

router = APIRouter(prefix="/crm", tags=["Mini CRM"])
STATIC = Path(__file__).with_name("static")
Identity = Annotated[dict, Depends(crm_identity)]
Days = Annotated[int, Query(ge=1, le=365)]
Page = Annotated[int, Query(ge=1, le=100000)]
Search = Annotated[str, Query(max_length=100)]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettingsUpdate(Payload):
    values: dict[str, str | int | float]


class VIPUpdate(Payload):
    names: list[str] = Field(max_length=100)


class NoteUpdate(Payload):
    note: str = Field(max_length=4000)


class ExpenseCreate(Payload):
    amount: Decimal = Field(gt=0, le=10000000, max_digits=12, decimal_places=2)
    currency: Literal["UAH", "USD", "EUR"] = "UAH"
    category: Literal["ads", "api", "printing", "delivery", "hosting", "other"]
    description: str = Field(min_length=1, max_length=500)
    occurred_on: date
    request_id: UUID


class VoidExpense(Payload):
    reason: str = Field(min_length=3, max_length=500)


class IntegrationUpdate(Payload):
    enabled: bool = False
    config: dict[str, str]
    credentials: dict[str, str] = Field(default_factory=dict)
    clear_credentials: bool = False


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def crm_page():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@router.get("/static/{filename}", include_in_schema=False)
async def crm_asset(filename: str):
    if filename not in {"crm.css", "crm.js"}:
        raise HTTPException(404)
    return FileResponse(STATIC / filename, headers={"Cache-Control": "no-store"})


@router.get("/api/session")
async def session_info(request: Request, identity: Identity):
    csrf = request.session.setdefault("crm_csrf", secrets.token_urlsafe(32))
    return {
        "actor": identity["actor"],
        "name": identity.get("first_name", "Администратор"),
        "owner": identity["owner"],
        "csrf": csrf,
    }


@router.get("/api/dashboard")
async def dashboard(identity: Identity, days: Days = 30):
    async with async_session_maker() as session:
        return await service.dashboard(session, days)


@router.post("/api/openai-costs/sync")
async def sync_openai_costs(request: Request, identity: Identity, days: Days = 35):
    """Owner-only manual reconciliation with the OpenAI organization cost ledger."""
    require_owner(identity)
    synchronizer = getattr(request.app.state, "openai_cost_sync", None)
    if synchronizer is None:
        raise HTTPException(503, "Синхронизатор расходов не запущен")
    if not synchronizer.configured:
        raise HTTPException(409, "OPENAI_ADMIN_API_KEY не настроен")
    try:
        imported = await synchronizer.sync_once(days=days)
    except Exception as exc:
        raise HTTPException(502, f"OpenAI cost sync failed: {type(exc).__name__}") from exc
    return {"ok": True, "imported": imported, "synced_at": synchronizer.last_synced_at}


@router.get("/api/orders")
async def orders(
    identity: Identity,
    days: Days = 30,
    page: Page = 1,
    search: Search = "",
    product: Literal["all", "menu", "gift"] = "all",
    payment: Literal["all", "cash", "stars", "vip", "unpaid", "unclassified"] = "all",
):
    async with async_session_maker() as session:
        return await service.orders_page(session, days, product, payment, search, page)


@router.get("/api/customers")
async def customers(identity: Identity, search: Search = "", page: Page = 1):
    async with async_session_maker() as session:
        return await service.customers_page(session, search, page)


@router.put("/api/customers/{telegram_id}/note")
async def customer_note(telegram_id: int, payload: NoteUpdate, identity: Identity):
    async with async_session_maker() as session:
        customer = await session.scalar(
            select(Customer.id).where(Customer.telegram_user_id == telegram_id)
        )
        gift = await session.scalar(
            select(WallpaperOrder.id).where(WallpaperOrder.telegram_user_id == telegram_id).limit(1)
        )
        if not customer and not gift:
            raise HTTPException(404, "Клиент не найден")
        row = await session.get(CustomerNote, str(telegram_id))
        if row:
            row.note, row.updated_by = payload.note, identity["actor"]
        else:
            session.add(
                CustomerNote(
                    telegram_user_id=str(telegram_id),
                    note=payload.note,
                    updated_by=identity["actor"],
                )
            )
        service.audit(session, identity["actor"], "customer.note", {"telegram_id": telegram_id})
        await session.commit()
    return {"ok": True}


@router.get("/api/settings")
async def settings(identity: Identity):
    async with async_session_maker() as session:
        result = await service.crm_settings(session)
    config = get_settings()
    result["services"] = {
        "portmone": PaymentService(config).portmone_ready,
        "mono": PaymentService(config).mono_ready,
        "smtp": bool(config.smtp_host and config.smtp_user),
        "openai": config.openai_api_key.get_secret_value() not in {"", "replace_me"},
        "openai_costs": config.openai_admin_api_key.get_secret_value() not in {"", "replace_me"},
        "encryption": bool(config.crm_encryption_key.get_secret_value()),
    }
    return result


@router.patch("/api/settings")
async def save_settings(payload: SettingsUpdate, identity: Identity):
    try:
        async with async_session_maker() as session:
            await service.save_settings(session, payload.values, identity["actor"])
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True}


@router.put("/api/vip")
async def save_vip(payload: VIPUpdate, identity: Identity):
    require_owner(identity)
    if any(not re.fullmatch(r"@?[A-Za-z0-9_]{5,32}", name) for name in payload.names):
        raise HTTPException(422, "Telegram username: от 5 до 32 латинских букв, цифр и _")
    names = list(dict.fromkeys(name.lstrip("@").casefold() for name in payload.names))
    async with async_session_maker() as session:
        row = await session.get(AppSetting, "vip_usernames")
        if row:
            row.value = ",".join(names)
        else:
            session.add(AppSetting(key="vip_usernames", value=",".join(names)))
        service.audit(session, identity["actor"], "access.vip", {"names": names})
        await session.commit()
    return {"vip": names}


def expense_dict(row):
    return {
        "id": row.id,
        "amount": service.money(row.amount),
        "currency": row.currency,
        "category": row.category,
        "description": row.description,
        "date": str(row.occurred_on),
        "voided": row.voided,
        "void_reason": row.void_reason,
        "created_by": row.created_by,
    }


@router.get("/api/expenses")
async def expenses(identity: Identity, days: Days = 30, page: Page = 1):
    begin, end = service.date_range(days)
    async with async_session_maker() as session:
        condition = [Expense.occurred_on >= begin.date(), Expense.occurred_on <= end.date()]
        total = await session.scalar(select(func.count(Expense.id)).where(*condition))
        rows = (
            (
                await session.execute(
                    select(Expense)
                    .where(*condition)
                    .order_by(Expense.occurred_on.desc(), Expense.created_at.desc())
                    .offset((page - 1) * 30)
                    .limit(30)
                )
            )
            .scalars()
            .all()
        )
        return {
            "items": [expense_dict(row) for row in rows],
            "total": total or 0,
            "page": page,
            "limit": 30,
        }


@router.post("/api/expenses")
async def add_expense(payload: ExpenseCreate, identity: Identity):
    if payload.occurred_on > datetime.now(UTC).date():
        raise HTTPException(422, "Расход не может иметь будущую дату")
    values = payload.model_dump(exclude={"request_id"})
    async with async_session_maker() as session:
        existing = await session.scalar(
            select(Expense).where(Expense.request_id == str(payload.request_id))
        )
        if not existing:
            row = Expense(
                **values, request_id=str(payload.request_id), created_by=identity["actor"]
            )
            session.add(row)
            service.audit(
                session,
                identity["actor"],
                "expense.create",
                {
                    "request_id": str(payload.request_id),
                    "amount": str(payload.amount),
                    "currency": payload.currency,
                    "category": payload.category,
                },
            )
            try:
                await session.commit()
                await session.refresh(row)
                return expense_dict(row)
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(Expense).where(Expense.request_id == str(payload.request_id))
                )
                if existing is None:
                    raise
        if existing.created_by != identity["actor"] or any(
            getattr(existing, key) != value for key, value in values.items()
        ):
            raise HTTPException(409, "Этот request_id уже использован для другого расхода")
        return expense_dict(existing)


@router.post("/api/expenses/{expense_id}/void")
async def void_expense(expense_id: UUID, payload: VoidExpense, identity: Identity):
    async with async_session_maker() as session:
        row = await session.get(Expense, str(expense_id), with_for_update=True)
        if row is None:
            raise HTTPException(404)
        if not row.voided:
            row.voided, row.void_reason = True, payload.reason
            service.audit(
                session, identity["actor"], "expense.void", {"id": row.id, "reason": payload.reason}
            )
            await session.commit()
    return {"ok": True}


@router.get("/api/ledger")
async def ledger(identity: Identity, page: Page = 1):
    from src.billing.models import Account, Transaction

    async with async_session_maker() as session:
        connection = await session.connection()
        available = await connection.run_sync(
            lambda conn: all(inspect(conn).has_table(name) for name in ("accounts", "transactions"))
        )
        if not available:
            return {"available": False, "items": [], "total": 0, "page": page, "limit": 30}
        balance = (
            await session.execute(
                select(func.sum(Account.available_balance), func.sum(Account.held_balance))
            )
        ).one()
        total = await session.scalar(select(func.count(Transaction.id)))
        rows = (
            await session.execute(
                select(Transaction, Account.owner_id)
                .join(Account)
                .order_by(Transaction.created_at.desc(), Transaction.id.desc())
                .offset((page - 1) * 30)
                .limit(30)
            )
        ).all()
        return {
            "available": True,
            "balance_minor": int(balance[0] or 0),
            "held_minor": int(balance[1] or 0),
            "total": total or 0,
            "page": page,
            "limit": 30,
            "items": [
                {
                    "id": row.id,
                    "owner": owner,
                    "amount_minor": row.amount,
                    "type": row.type.value,
                    "reference": row.reference_id,
                    "description": row.description,
                    "date": row.created_at.isoformat(),
                }
                for row, owner in rows
            ],
        }


def integration_public(row):
    return {
        "provider": row.provider,
        "enabled": row.enabled,
        "config": row.config,
        "credentials_saved": bool(row.encrypted_secrets),
        "status": row.status,
        "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
        "last_error": row.last_error,
        "report": row.report,
    }


@router.get("/api/integrations")
async def advertising(identity: Identity):
    async with async_session_maker() as session:
        rows = (await session.execute(select(Integration))).scalars().all()
        return {"items": [integration_public(row) for row in rows]}


@router.put("/api/integrations/{provider}")
async def save_advertising(
    provider: Literal["meta", "google_ads"], payload: IntegrationUpdate, identity: Identity
):
    require_owner(identity)
    try:
        config, credentials = integrations.validate_configuration(
            provider, payload.config, payload.credentials
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    async with async_session_maker() as session:
        row = await session.get(Integration, provider, with_for_update=True)
        if row is None:
            row = Integration(provider=provider, encrypted_secrets="")
            session.add(row)
        previous = {} if payload.clear_credentials else decrypt_credentials(row.encrypted_secrets)
        previous.update(credentials)
        row.config, row.enabled = config, payload.enabled
        row.encrypted_secrets = encrypt_credentials(previous) if previous else ""
        row.status, row.last_error, row.report, row.last_checked_at = (
            "not_checked",
            None,
            None,
            None,
        )
        service.audit(
            session,
            identity["actor"],
            "integration.update",
            {
                "provider": provider,
                "enabled": row.enabled,
                "config": config,
                "secret_fields_changed": sorted(credentials),
                "credentials_cleared": payload.clear_credentials,
            },
        )
        await session.commit()
        await session.refresh(row)
        return integration_public(row)


@router.post("/api/integrations/{provider}/sync")
async def sync_advertising(
    provider: Literal["meta", "google_ads"], identity: Identity, days: Days = 30
):
    require_owner(identity)
    async with async_session_maker() as session:
        row = await session.get(Integration, provider)
        if row is None or not row.enabled:
            raise HTTPException(409, "Сначала сохраните и включите интеграцию")
        config, ciphertext = dict(row.config), row.encrypted_secrets
        credentials = decrypt_credentials(ciphertext)
    error = None
    try:
        report = await integrations.fetch_report(provider, config, credentials, days)
    except (integrations.ProviderError, ValueError, KeyError, TypeError) as exc:
        # Never persist provider response bodies, OAuth tokens or secrets.
        error = (
            str(exc)
            if isinstance(exc, integrations.ProviderError)
            else "Не удалось прочитать рекламный отчёт"
        )
        report = None
    async with async_session_maker() as session:
        row = await session.get(Integration, provider, with_for_update=True)
        if row.config != config or row.encrypted_secrets != ciphertext:
            raise HTTPException(
                409, "Настройки изменились во время синхронизации. Повторите запрос."
            )
        row.last_checked_at, row.last_error = datetime.now(UTC), error
        row.status = "error" if error else "connected"
        if report is not None:
            row.report = report
        service.audit(
            session,
            identity["actor"],
            "integration.sync",
            {"provider": provider, "days": days, "ok": error is None},
        )
        await session.commit()
        await session.refresh(row)
        return integration_public(row)


@router.get("/api/audit")
async def audit_log(identity: Identity, page: Page = 1):
    async with async_session_maker() as session:
        total = await session.scalar(select(func.count(Audit.id)))
        rows = (
            (
                await session.execute(
                    select(Audit)
                    .order_by(Audit.created_at.desc())
                    .offset((page - 1) * 30)
                    .limit(30)
                )
            )
            .scalars()
            .all()
        )
        return {
            "items": [
                {
                    "actor": row.actor,
                    "action": row.action,
                    "details": row.details,
                    "date": row.created_at.isoformat(),
                }
                for row in rows
            ],
            "total": total or 0,
            "page": page,
            "limit": 30,
        }


@router.get("/api/export/{kind}")
async def export(
    kind: Literal["customers", "orders"],
    identity: Identity,
    days: Days = 30,
    search: Search = "",
    product: Literal["all", "menu", "gift"] = "all",
    payment: Literal["all", "cash", "stars", "vip", "unpaid", "unclassified"] = "all",
):
    async with async_session_maker() as session:
        if kind == "customers":
            result = await service.customers_page(session, search=search, limit=10000)
            columns = [
                "telegram_id",
                "name",
                "phone",
                "country",
                "city",
                "language",
                "orders",
                "paid_orders",
                "note",
            ]
        else:
            result = await service.orders_page(session, days, product, payment, search, limit=10000)
            columns = [
                "product",
                "id",
                "telegram_id",
                "name",
                "status",
                "payment_kind",
                "amount",
                "stars",
                "provider",
                "created_at",
            ]
        if result["total"] > 10000:
            raise HTTPException(422, "Сузьте фильтр: экспорт содержит более 10 000 записей")
        service.audit(session, identity["actor"], "export", {"kind": kind, "rows": result["total"]})
        await session.commit()
    return Response(
        service.export_csv(result["items"], columns),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="foodporn_{kind}.csv"',
            "Cache-Control": "no-store",
        },
    )
