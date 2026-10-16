"""
==========================================================
FOOD_PORN

Module: Roadmap v1 Regression Tests
Layer: Tests

Critical coverage for omnichannel authentication, provider costs,
commercial analytics and scheduled gift delivery.
==========================================================
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.channels.router import _meta_events
from app.config import Settings
from app.crm.models import CRMBase, Expense
from app.crm.service import dashboard
from app.database.models import (
    AIGenerationLog,
    Base,
    CurrencyRate,
    Customer,
    Language,
    Menu,
    MenuStatus,
    ProviderCost,
    ScheduledDelivery,
)
from app.miniapp import auth
from app.services import scheduled_delivery
from app.services.dish_input import normalize_dish_payload
from app.services.openai_costs import OpenAICostSynchronizer
from app.services.scheduled_delivery import ScheduledDeliveryWorker


@pytest.fixture
async def database(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "roadmap.db"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(CRMBase.metadata.create_all)
    yield factory
    await engine.dispose()


def test_plain_dish_list_and_categorized_rows_share_one_contract():
    simple = normalize_dish_payload(
        {
            "mode": "list",
            "text": "1. Стейк\nЗакуска: брускетта\nпас\nДесерт: тирамису\nНапиток: лимонад",
        }
    )
    assert [item["title"] for item in simple] == [
        "Стейк",
        "брускетта",
        "тирамису",
        "лимонад",
    ]
    assert [item["category"] for item in simple] == [
        "main",
        "appetizer",
        "dessert",
        "drink",
    ]

    categorized = normalize_dish_payload(
        [
            {"category": "main", "title": " Плов "},
            {"category": "drink", "title": "pass"},
        ]
    )
    assert categorized == [{"category": "main", "title": "Плов"}]


def test_channel_token_round_trip_tamper_and_expiry(monkeypatch):
    settings = Settings(
        _env_file=None,
        channel_link_secret=SecretStr("roadmap-test-secret-that-is-long-enough"),
        channel_link_ttl_hours=1,
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    token = auth.create_channel_token(
        "whatsapp", "380501234567", name="Anna", language="uk", now=1_000
    )
    user = auth.verify_channel_token(token, now=1_001)

    assert user["source_channel"] == "whatsapp"
    assert user["external_user_id"] == "380501234567"
    assert user["first_name"] == "Anna"
    assert user["id"] == auth.channel_internal_user_id("whatsapp", "380501234567")

    with pytest.raises(HTTPException) as tampered:
        auth.verify_channel_token(token + "x", now=1_001)
    assert tampered.value.status_code == 401

    with pytest.raises(HTTPException) as expired:
        auth.verify_channel_token(token, now=4_601)
    assert expired.value.status_code == 401


def test_meta_webhook_normalization_for_whatsapp_messenger_and_instagram():
    whatsapp = _meta_events(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "contacts": [
                                    {"wa_id": "38050", "profile": {"name": "Anna"}}
                                ],
                                "messages": [
                                    {
                                        "id": "wamid.1",
                                        "from": "38050",
                                        "text": {"body": "start"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ],
        }
    )
    assert len(whatsapp) == 1
    assert (whatsapp[0].channel, whatsapp[0].sender_id, whatsapp[0].display_name) == (
        "whatsapp",
        "38050",
        "Anna",
    )

    for object_name, expected in (("page", "messenger"), ("instagram", "instagram")):
        events = _meta_events(
            {
                "object": object_name,
                "entry": [
                    {
                        "messaging": [
                            {
                                "sender": {"id": "user-1"},
                                "message": {"mid": "event-1", "text": "hello"},
                            }
                        ]
                    }
                ],
            }
        )
        assert len(events) == 1
        assert events[0].channel == expected
        assert events[0].event_id == "event-1"


async def test_openai_cost_sync_is_idempotent(database, monkeypatch):
    settings = Settings(
        _env_file=None,
        openai_admin_api_key=SecretStr("admin-key-for-test"),
        openai_project_id="proj_food_porn",
    )
    synchronizer = OpenAICostSynchronizer(settings, database)
    payload = [
        {
            "start_time": 1_700_000_000,
            "end_time": 1_700_086_400,
            "results": [
                {
                    "amount": {"value": 1.25, "currency": "usd"},
                    "line_item": "images",
                    "project_id": "proj_food_porn",
                    "organization_id": "org-test",
                }
            ],
        }
    ]
    monkeypatch.setattr(synchronizer, "_fetch", AsyncMock(return_value=payload))

    assert await synchronizer.sync_once(days=30) == 1
    assert await synchronizer.sync_once(days=30) == 0
    async with database() as session:
        assert await session.scalar(select(func.count(ProviderCost.id))) == 1


async def test_dashboard_uses_paid_at_and_actual_openai_cost(database):
    now = datetime.now(UTC)
    async with database() as session:
        customer = Customer(
            telegram_user_id=10,
            name="Client",
            phone="+380000000000",
            language=Language.UK,
            country="Ukraine",
            city="Kyiv",
        )
        session.add(customer)
        await session.flush()
        session.add_all(
            [
                Menu(
                    customer_id=customer.id,
                    status=MenuStatus.COMPLETED,
                    is_paid=True,
                    payment_system="portmone",
                    price_amount=Decimal("100"),
                    paid_at=now,
                ),
                Menu(
                    customer_id=customer.id,
                    status=MenuStatus.COMPLETED,
                    is_paid=True,
                    payment_system="vip_bypass",
                    price_amount=Decimal("500"),
                    paid_at=now,
                ),
                Menu(
                    customer_id=customer.id,
                    status=MenuStatus.DRAFT,
                    is_paid=False,
                    price_amount=Decimal("500"),
                ),
                AIGenerationLog(
                    user_id=10,
                    model_name="gpt-image-test",
                    cost_usd=Decimal("1"),
                    exchange_rate=Decimal("40"),
                    cost_uah=Decimal("40"),
                ),
                ProviderCost(
                    provider="openai",
                    external_key="actual-openai-test",
                    bucket_start=now,
                    bucket_end=now + timedelta(days=1),
                    amount=Decimal("2"),
                    currency="usd",
                    project_id="proj_food_porn",
                ),
                CurrencyRate(date=now.date().isoformat(), rate=Decimal("40")),
                Expense(
                    amount=Decimal("10"),
                    currency="UAH",
                    category="hosting",
                    description="Railway",
                    occurred_on=now.date(),
                    created_by="test",
                    request_id="roadmap-expense-test",
                ),
            ]
        )
        await session.commit()

        result = await dashboard(session, days=30)

    assert result["orders"] == 3
    assert result["qualified_orders"] == 2
    assert result["draft_orders"] == 1
    assert result["commercial_opportunities"] == 1
    assert result["paid_orders"] == 1
    assert result["vip_orders"] == 1
    assert result["conversion"] == 100.0
    assert result["revenue_uah"] == "100.00"
    assert result["ai_costs"]["source"] == "openai_actual"
    assert result["ai_costs"]["effective_uah"] == "80.00"
    assert result["expenses_total_uah"] == "90.00"
    assert result["balance_uah"] == "10.00"


async def test_scheduled_delivery_sends_once(database, tmp_path, monkeypatch):
    attachment = tmp_path / "gift.pdf"
    attachment.write_bytes(b"pdf")
    async with database() as session:
        session.add(
            ScheduledDelivery(
                owner_user_id=42,
                kind="gift",
                reference_id="gift-7",
                recipient_email="recipient@example.com",
                subject="Your gift",
                attachments=[str(attachment)],
                send_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        await session.commit()

    sender = AsyncMock()
    monkeypatch.setattr(scheduled_delivery, "send_ready_order_email", sender)
    worker = ScheduledDeliveryWorker(database)

    assert await worker.run_due() == 1
    assert await worker.run_due() == 0
    sender.assert_awaited_once()
    async with database() as session:
        row = await session.scalar(select(ScheduledDelivery))
        assert row.status == "sent"
        assert row.sent_at is not None
        assert row.attempts == 1
