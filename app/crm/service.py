"""Database-backed CRM queries. Money and Telegram Stars stay separate."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import String, case, cast, func, literal, or_, select, union, union_all

from app.config import get_settings
from app.crm.models import Audit, CustomerNote, Expense
from app.database.models import (
    AIGenerationLog,
    AppSetting,
    CurrencyRate,
    Customer,
    Menu,
    ProviderCost,
    WallpaperOrder,
)
from app.services.settings_service import get_setting, get_vip_users

CASH_PROVIDERS = ("mono", "portmone", "redsys", "liqpay", "wayforpay", "paypal")
FREE_PROVIDERS = ("vip_bypass", "vip", "free")
SETTING_RULES = {
    "menu_price_uah": (Decimal("1"), Decimal("100000"), False, None),
    "menu_price_stars": (Decimal("0"), Decimal("100000"), True, "menu_price_stars"),
    "gift_price_stars": (Decimal("0"), Decimal("100000"), True, "gift_price_stars"),
    "usd_exchange_rate": (Decimal("0.01"), Decimal("10000"), False, "usd_exchange_rate"),
    "price_electronic_uah": (Decimal("1"), Decimal("100000"), True, "price_electronic_uah"),
    "price_print_uah": (Decimal("1"), Decimal("100000"), True, "price_print_uah"),
}


def audit(session, actor: str, action: str, details: dict) -> None:
    session.add(Audit(actor=actor, action=action, details=details))


def money(value) -> str:
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def date_range(days: int) -> tuple[datetime, datetime]:
    end = datetime.now(UTC)
    return datetime.combine((end - timedelta(days=days - 1)).date(), datetime.min.time(), UTC), end


def order_queries():
    def payment_kind(paid, provider):
        return case(
            (~paid, literal("unpaid")),
            (provider.in_(FREE_PROVIDERS), literal("vip")),
            (provider == "telegram_stars", literal("stars")),
            (provider.in_(CASH_PROVIDERS), literal("cash")),
            else_=literal("unclassified"),
        )

    menus = select(
        Menu.id.label("id"),
        literal("menu").label("product"),
        Customer.telegram_user_id.label("telegram_id"),
        Customer.name.label("name"),
        cast(Menu.status, String).label("status"),
        Menu.is_paid.label("paid"),
        Menu.price_amount.label("amount"),
        Menu.stars_amount.label("stars"),
        Menu.payment_system.label("provider"),
        Menu.payment_id.label("payment_id"),
        Menu.error_message.label("error"),
        Menu.created_at.label("created_at"),
        func.coalesce(Menu.paid_at, case((Menu.is_paid, Menu.created_at))).label("paid_at"),
        Menu.source_channel.label("source_channel"),
        func.lower(cast(Menu.status, String)).in_((
            "queued", "images_ready", "waiting_for_payment", "paid",
            "sent_to_printshop", "completed", "failed",
        )).label("qualified"),
        payment_kind(Menu.is_paid, Menu.payment_system).label("payment_kind"),
    ).join(Customer, Menu.customer_id == Customer.id)
    gifts = select(
        WallpaperOrder.id,
        literal("gift"),
        WallpaperOrder.telegram_user_id,
        func.coalesce(Customer.name, literal("Клиент Telegram")),
        case((WallpaperOrder.paid, literal("ready")), else_=literal("waiting_for_payment")),
        WallpaperOrder.paid,
        WallpaperOrder.amount,
        WallpaperOrder.stars_amount,
        WallpaperOrder.payment_system,
        WallpaperOrder.payment_id,
        literal(None),
        WallpaperOrder.created_at,
        func.coalesce(
            WallpaperOrder.paid_at,
            case((WallpaperOrder.paid, WallpaperOrder.created_at)),
        ),
        WallpaperOrder.source_channel,
        literal(True),
        payment_kind(WallpaperOrder.paid, WallpaperOrder.payment_system),
    ).outerjoin(Customer, WallpaperOrder.telegram_user_id == Customer.telegram_user_id)
    return union_all(menus, gifts).cte("crm_orders")


def order_conditions(
    orders, days: int, product: str = "all", payment: str = "all", search: str = ""
):
    begin, end = date_range(days)
    conditions = [orders.c.created_at >= begin, orders.c.created_at <= end]
    if product != "all":
        conditions.append(orders.c.product == product)
    if payment != "all":
        conditions.append(orders.c.payment_kind == payment)
    if search:
        term = f"%{search}%"
        conditions.append(
            or_(
                orders.c.name.ilike(term),
                cast(orders.c.telegram_id, String).ilike(term),
                cast(orders.c.id, String).ilike(term),
            )
        )
    return conditions


async def orders_page(session, days=30, product="all", payment="all", search="", page=1, limit=30):
    orders = order_queries()
    conditions = order_conditions(orders, days, product, payment, search)
    total = await session.scalar(select(func.count()).select_from(orders).where(*conditions))
    rows = (
        (
            await session.execute(
                select(orders)
                .where(*conditions)
                .order_by(orders.c.created_at.desc(), orders.c.product, orders.c.id.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        )
        .mappings()
        .all()
    )
    result = []
    for item in rows:
        row = dict(item)
        row["amount"] = money(row["amount"])
        row["created_at"] = row["created_at"].isoformat() if row["created_at"] else None
        row["status"] = str(row["status"]).lower()
        result.append(row)
    return {"items": result, "total": total or 0, "page": page, "limit": limit}


async def dashboard(session, days: int = 30) -> dict:
    orders = order_queries()
    conditions = order_conditions(orders, days)
    fields = orders.c
    aggregate = (
        (
            await session.execute(
                select(
                    func.count().label("orders"),
                    func.sum(case((fields.product == "menu", 1), else_=0)).label("menus"),
                    func.sum(case((fields.product == "gift", 1), else_=0)).label("gifts"),
                    func.sum(
                        case(
                            (
                                (fields.product == "gift")
                                & fields.payment_kind.in_(("cash", "stars")),
                                1,
                            ),
                            else_=0,
                        )
                    ).label("paid_gifts"),
                    func.sum(case((fields.payment_kind.in_(("cash", "stars")), 1), else_=0)).label(
                        "paid_orders"
                    ),
                    func.sum(case((fields.payment_kind == "vip", 1), else_=0)).label("vip_orders"),
                    func.sum(case((fields.payment_kind == "unpaid", 1), else_=0)).label(
                        "unpaid_orders"
                    ),
                    func.sum(case((fields.payment_kind == "unclassified", 1), else_=0)).label(
                        "unclassified_orders"
                    ),
                    func.sum(case((fields.qualified.is_(True), 1), else_=0)).label("qualified_orders"),
                    func.sum(case((fields.qualified.is_(False), 1), else_=0)).label("draft_orders"),
                    func.sum(case((
                        fields.qualified.is_(True) & (fields.payment_kind != "vip"), 1
                    ), else_=0)).label("commercial_opportunities"),
                ).where(*conditions)
            )
        )
        .mappings()
        .one()
    )
    result = {key: int(value or 0) for key, value in aggregate.items()}
    begin, end = date_range(days)
    revenue = (
        await session.execute(
            select(
                func.sum(case((fields.payment_kind == "cash", fields.amount), else_=0)),
                func.sum(case((fields.payment_kind == "stars", fields.stars), else_=0)),
            ).where(fields.paid_at >= begin, fields.paid_at <= end)
        )
    ).one()
    result["revenue_uah"] = money(revenue[0])
    result["revenue_stars"] = int(revenue[1] or 0)
    identities = union(
        select(Customer.telegram_user_id), select(WallpaperOrder.telegram_user_id)
    ).subquery()
    result["customers_total"] = await session.scalar(
        select(func.count()).select_from(identities)
    ) or 0
    result["customers"] = await session.scalar(
        select(func.count(func.distinct(fields.telegram_id))).where(*conditions)
    ) or 0
    result["conversion"] = round(
        result["paid_orders"] / max(result["commercial_opportunities"], 1) * 100, 1
    )
    expenses = (
        await session.execute(
            select(Expense.currency, func.sum(Expense.amount))
            .where(
                Expense.voided.is_(False),
                Expense.occurred_on >= begin.date(),
                Expense.occurred_on <= end.date(),
            )
            .group_by(Expense.currency)
        )
    ).all()
    result["expenses"] = {currency: money(amount) for currency, amount in expenses}
    ai_row = (
        await session.execute(
            select(
                func.count(AIGenerationLog.id),
                func.sum(AIGenerationLog.cost_usd),
                func.sum(AIGenerationLog.cost_uah),
            ).where(AIGenerationLog.created_at >= begin, AIGenerationLog.created_at <= end)
        )
    ).one()
    actual_usd = await session.scalar(
        select(func.sum(ProviderCost.amount)).where(
            ProviderCost.provider == "openai",
            ProviderCost.currency == "usd",
            ProviderCost.bucket_start >= begin,
            ProviderCost.bucket_start <= end,
        )
    ) or Decimal(0)
    latest_rate = await session.scalar(select(CurrencyRate.rate).order_by(CurrencyRate.date.desc()))
    exchange_rate = Decimal(latest_rate or str(get_settings().usd_exchange_rate))
    local_ai_usd = Decimal(ai_row[1] or 0)
    local_ai_uah = Decimal(ai_row[2] or 0)
    actual_ai_uah = Decimal(actual_usd) * exchange_rate
    selected_ai_uah = actual_ai_uah if actual_usd else local_ai_uah
    result["ai_costs"] = {
        "operations": int(ai_row[0] or 0),
        "estimated_usd": money(local_ai_usd),
        "estimated_uah": money(local_ai_uah),
        "actual_usd": money(actual_usd),
        "actual_uah": money(actual_ai_uah),
        "effective_uah": money(selected_ai_uah),
        "source": "openai_actual" if actual_usd else "local_estimate",
    }
    manual_uah = Decimal(result["expenses"].get("UAH", "0"))
    result["expenses_total_uah"] = money(manual_uah + selected_ai_uah)
    result["balance_uah"] = money(
        Decimal(result["revenue_uah"]) - manual_uah - selected_ai_uah
    )
    daily = (
        (
            await session.execute(
                select(
                    func.date(fields.created_at).label("day"),
                    func.count().label("orders"),
                    func.sum(case((fields.payment_kind.in_(("cash", "stars")), 1), else_=0)).label(
                        "paid"
                    ),
                )
                .where(*conditions)
                .group_by(func.date(fields.created_at))
            )
        )
        .mappings()
        .all()
    )
    indexed = {str(row["day"]): dict(row) for row in daily}
    result["daily"] = [
        indexed.get(
            str(begin.date() + timedelta(days=i)),
            {"day": str(begin.date() + timedelta(days=i)), "orders": 0, "paid": 0},
        )
        for i in range(days)
    ]
    result["recent"] = (await orders_page(session, days=days, limit=8))["items"]
    result["days"] = days
    result["period_basis"] = {
        "orders": "created_at",
        "revenue": "paid_at",
        "expenses": "occurred_on",
        "ai": "provider bucket or generation time",
    }
    return result


async def customers_page(session, search="", page=1, limit=30):
    ids = union(
        select(Customer.telegram_user_id.label("uid")), select(WallpaperOrder.telegram_user_id)
    ).cte("crm_customers")
    orders = order_queries()
    counts = (
        select(
            orders.c.telegram_id,
            func.count().label("orders"),
            func.sum(case((orders.c.payment_kind.in_(("cash", "stars")), 1), else_=0)).label(
                "paid_orders"
            ),
        )
        .group_by(orders.c.telegram_id)
        .cte("customer_orders")
    )
    query = select(
        ids.c.uid.label("telegram_id"),
        Customer.id,
        Customer.name,
        Customer.phone,
        Customer.language,
        Customer.country,
        Customer.city,
        Customer.last_seen_at,
        func.coalesce(counts.c.orders, 0).label("orders"),
        func.coalesce(counts.c.paid_orders, 0).label("paid_orders"),
        CustomerNote.note,
    ).outerjoin(Customer, ids.c.uid == Customer.telegram_user_id)
    query = query.outerjoin(counts, counts.c.telegram_id == ids.c.uid)
    query = query.outerjoin(CustomerNote, CustomerNote.telegram_user_id == cast(ids.c.uid, String))
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                Customer.name.ilike(term),
                Customer.phone.ilike(term),
                cast(ids.c.uid, String).ilike(term),
            )
        )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        (
            await session.execute(
                query.order_by(ids.c.uid.desc()).offset((page - 1) * limit).limit(limit)
            )
        )
        .mappings()
        .all()
    )
    items = []
    for value in rows:
        row = dict(value)
        row["language"] = row["language"].value if row["language"] else None
        row["last_seen_at"] = row["last_seen_at"].isoformat() if row["last_seen_at"] else None
        items.append(row)
    return {"items": items, "total": total or 0, "page": page, "limit": limit}


async def crm_settings(session) -> dict:
    settings = get_settings()
    values = {}
    for key, (_, _, _, attribute) in SETTING_RULES.items():
        default = getattr(settings, attribute) if attribute else settings.menu_price
        values[key] = await get_setting(session, key, str(default))
    return {
        "values": values,
        "vip": await get_vip_users(session, settings.default_vip_users),
        "owner_ids": list(settings.admin_telegram_ids),
        "gift_price_policy": "Measured API cost + 5%",
    }


def validate_settings(values: dict) -> dict[str, str]:
    if not values or set(values) - SETTING_RULES.keys():
        raise ValueError("Неизвестные параметры")
    normalized = {}
    for key, value in values.items():
        number = Decimal(str(value))
        low, high, integer, _ = SETTING_RULES[key]
        if (
            not number.is_finite()
            or not low <= number <= high
            or (integer and number != number.to_integral_value())
        ):
            raise ValueError(f"{key}: допустимый диапазон {low}–{high}")
        normalized[key] = str(int(number)) if integer else money(number)
    return normalized


async def save_settings(session, values: dict, actor: str) -> None:
    normalized = validate_settings(values)
    before = {}
    for key, value in normalized.items():
        row = await session.get(AppSetting, key)
        before[key] = row.value if row else None
        if row:
            row.value = value
        else:
            session.add(AppSetting(key=key, value=value, description="Mini CRM commercial setting"))
    audit(session, actor, "settings.update", {"before": before, "after": normalized})
    await session.commit()
    apply_runtime_values(normalized)


def apply_runtime_values(values: dict) -> None:
    settings = get_settings()
    for key, value in values.items():
        _, _, integer, attribute = SETTING_RULES[key]
        if attribute:
            setattr(settings, attribute, int(value) if integer else float(value))


async def load_runtime_settings(session_factory) -> None:
    async with session_factory() as session:
        rows = (
            (await session.execute(select(AppSetting).where(AppSetting.key.in_(SETTING_RULES))))
            .scalars()
            .all()
        )
    # Bad historical values are reported at startup, never applied silently.
    if rows:
        apply_runtime_values(validate_settings({row.key: row.value for row in rows}))


def export_csv(rows: list[dict], columns: list[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(columns)
    for row in rows:
        values = []
        for column in columns:
            value = str(row.get(column) if row.get(column) is not None else "")
            # Neutralize spreadsheet formulas in customer-supplied text.
            if value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return "\ufeff" + buffer.getvalue()
