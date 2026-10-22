"""Mini CRM regressions: permissions, accounting, encryption and real DB writes."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.admin_app as webadmin
import main
from app.bot.handlers import admin, start
from app.config import Settings
from app.crm import integrations, router, security, service
from app.crm.models import Audit, CRMBase, Expense, Integration
from app.database.models import (
    AppSetting,
    Base,
    Customer,
    Language,
    Menu,
    MenuStatus,
    WallpaperOrder,
)
from app.miniapp import api, auth
from app.services.admin_access import crm_url, has_admin_access


def signed(user_id=42, username=None):
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": user_id, "first_name": "Admin", "username": username}),
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", b"123:test", hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return {"Authorization": "tma " + urlencode(fields)}


@pytest.fixture
async def crm(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "crm.db"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(CRMBase.metadata.create_all)
    settings = Settings(
        _env_file=None,
        bot_token="123:test",
        admin_telegram_ids=(42,),
        default_vip_users=["VipPerson"],
        miniapp_url="https://example.org/miniapp",
        crm_encryption_key=SecretStr(Fernet.generate_key().decode()),
        admin_username="owner",
        admin_password=SecretStr("password-for-test"),
    )
    for module in (router, security, api, start, admin):
        monkeypatch.setattr(module, "async_session_maker", factory)
    for module in (router, security, service, api, start, admin, webadmin, auth):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test", trust_env=False
    ) as client:
        yield SimpleNamespace(engine=engine, factory=factory, settings=settings, client=client)
    await engine.dispose()


async def seed(crm):
    async with crm.factory() as session:
        client = Customer(
            id=1,
            telegram_user_id=10,
            name="Client A",
            phone="+380000",
            language=Language.UK,
            country="Ukraine",
            city="Kyiv",
        )
        session.add(client)
        for identifier, paid, provider, amount, stars in [
            (1, True, "portmone", 100, None),
            (2, True, "vip_bypass", 500, None),
            (3, True, "telegram_stars", 250, 15),
            (4, False, None, 500, None),
            (5, True, None, 100, None),
        ]:
            session.add(
                Menu(
                    id=identifier,
                    customer_id=1,
                    status=MenuStatus.COMPLETED if paid else MenuStatus.DRAFT,
                    is_paid=paid,
                    payment_system=provider,
                    price_amount=Decimal(amount),
                    stars_amount=stars,
                )
            )
        session.add_all(
            [
                WallpaperOrder(
                    id=1,
                    telegram_user_id=77,
                    amount=Decimal(200),
                    mobile_path="a.png",
                    desktop_path="b.png",
                    paid=True,
                    payment_system="portmone",
                ),
                WallpaperOrder(
                    id=2,
                    telegram_user_id=88,
                    amount=Decimal(0),
                    mobile_path="a.png",
                    desktop_path="b.png",
                    paid=True,
                    payment_system="vip_bypass",
                ),
                Expense(
                    amount=Decimal(30),
                    currency="UAH",
                    category="api",
                    description="AI",
                    occurred_on=datetime.now(UTC).date(),
                    created_by="test",
                    request_id=str(uuid.uuid4()),
                ),
                Expense(
                    amount=Decimal(99),
                    currency="USD",
                    category="ads",
                    description="Ads",
                    occurred_on=datetime.now(UTC).date(),
                    created_by="test",
                    request_id=str(uuid.uuid4()),
                ),
            ]
        )
        await session.commit()


async def test_dynamic_vip_policy_and_revocation(crm):
    assert await has_admin_access(42, None, crm.settings, crm.factory)
    assert await has_admin_access(12, "@VIPPERSON", crm.settings, crm.factory)
    assert not await has_admin_access(13, "stranger", crm.settings, crm.factory)
    async with crm.factory() as session:
        session.add(AppSetting(key="vip_usernames", value="DifferentPerson"))
        await session.commit()
    assert not await has_admin_access(12, "VipPerson", crm.settings, crm.factory)
    assert await has_admin_access(12, "differentperson", crm.settings, crm.factory)
    assert await has_admin_access(42, None, crm.settings, crm.factory)


async def test_free_id_does_not_implicitly_grant_crm(crm):
    crm.settings.free_generation_telegram_ids = (90,)
    assert not await has_admin_access(90, None, crm.settings, crm.factory)


async def test_vip_button_in_legacy_menu_and_miniapp(crm, monkeypatch):
    user = SimpleNamespace(id=12, username="VipPerson", first_name="VIP")
    keyboard = await start.get_user_products_menu_keyboard(user, "ru")
    assert any(
        button.callback_data == "admin_home" for row in keyboard.inline_keyboard for button in row
    )
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={}), clear=AsyncMock(), update_data=AsyncMock()
    )
    monkeypatch.setattr(start, "preferred_language", AsyncMock(return_value="ru"))
    message = SimpleNamespace(from_user=user, answer=AsyncMock())
    await start.cmd_start(message, state)
    keyboard = message.answer.call_args.kwargs["reply_markup"]
    assert any(
        button.web_app and button.web_app.url == "https://example.org/crm"
        for row in keyboard.inline_keyboard
        for button in row
    )
    user.username = "stranger"
    await start.cmd_start(message, state)
    keyboard = message.answer.call_args.kwargs["reply_markup"]
    assert not any(
        button.web_app and "/crm" in button.web_app.url
        for row in keyboard.inline_keyboard
        for button in row
    )


async def test_middleware_vip_and_no_username(crm):
    event = SimpleNamespace(
        from_user=SimpleNamespace(id=12, username="vipperson"), answer=AsyncMock()
    )
    handler = AsyncMock()
    await admin.AdminOnly()(handler, event, {})
    handler.assert_awaited_once()
    event.from_user = SimpleNamespace(id=13)
    await admin.AdminOnly()(handler, event, {})
    assert handler.await_count == 1
    event.answer.assert_awaited_once()


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard",
        "/orders",
        "/customers",
        "/settings",
        "/expenses",
        "/ledger",
        "/integrations",
        "/audit",
        "/export/customers",
    ],
)
async def test_crm_rejects_unsigned_and_non_admin(crm, path):
    assert (await crm.client.get("/crm/api" + path)).status_code == 401
    assert (
        await crm.client.get("/crm/api" + path, headers=signed(99, "stranger"))
    ).status_code == 403


async def test_vip_can_read_crm_and_legacy_admin_but_not_change_access(crm):
    header = signed(12, "vipperson")
    assert (await crm.client.get("/crm/api/dashboard", headers=header)).status_code == 200
    assert (await crm.client.get("/miniapp/api/admin", headers=header)).status_code == 200
    result = await crm.client.put("/crm/api/vip", headers=header, json={"names": ["newadmin"]})
    assert result.status_code == 403
    assert (
        await crm.client.put(
            "/crm/api/integrations/meta",
            headers=header,
            json={"config": {"ad_account_id": "123456"}, "enabled": True},
        )
    ).status_code == 403


async def test_dashboard_separates_vip_stars_cash_and_unclassified(crm):
    await seed(crm)
    result = (await crm.client.get("/crm/api/dashboard", headers=signed())).json()
    assert result["orders"] == 7
    assert result["revenue_uah"] == "300.00"
    assert result["revenue_stars"] == 15
    assert result["vip_orders"] == 2
    assert result["unclassified_orders"] == 1
    assert result["paid_orders"] == 3
    assert result["customers"] == 3
    assert result["balance_uah"] == "270.00"
    assert result["expenses"] == {"UAH": "30.00", "USD": "99.00"}


async def test_order_filter_search_and_customers_without_registration(crm):
    await seed(crm)
    result = (
        await crm.client.get("/crm/api/orders?product=gift&payment=vip", headers=signed())
    ).json()
    assert len(result["items"]) == 1 and result["items"][0]["telegram_id"] == 88
    result = (await crm.client.get("/crm/api/customers?search=77", headers=signed())).json()
    assert result["total"] == 1 and result["items"][0]["id"] is None
    assert (
        await crm.client.put(
            "/crm/api/customers/77/note", headers=signed(), json={"note": "<script>unsafe</script>"}
        )
    ).status_code == 200
    result = (await crm.client.get("/crm/api/customers?search=77", headers=signed())).json()
    assert result["items"][0]["note"] == "<script>unsafe</script>"


async def test_expense_idempotency_and_void(crm):
    payload = {
        "amount": "12.50",
        "currency": "UAH",
        "category": "api",
        "description": "Generation",
        "occurred_on": str(datetime.now(UTC).date()),
        "request_id": str(uuid.uuid4()),
    }
    first = await crm.client.post("/crm/api/expenses", headers=signed(), json=payload)
    second = await crm.client.post("/crm/api/expenses", headers=signed(), json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert (
        await crm.client.post(
            "/crm/api/expenses", headers=signed(), json={**payload, "amount": "99"}
        )
    ).status_code == 409
    async with crm.factory() as session:
        assert await session.scalar(select(func.count(Expense.id))) == 1
    assert (
        await crm.client.post(
            "/crm/api/expenses/" + first.json()["id"] + "/void",
            headers=signed(),
            json={"reason": "Duplicate record"},
        )
    ).status_code == 200
    stats = (await crm.client.get("/crm/api/dashboard", headers=signed())).json()
    assert stats["expenses"] == {}
    async with crm.factory() as session:
        assert (await session.get(Expense, first.json()["id"])).voided
        actions = (await session.execute(select(Audit.action))).scalars().all()
        assert actions == ["expense.create", "expense.void"]


@pytest.mark.parametrize("amount", ["-1", "0", "NaN", "12.123"])
async def test_invalid_expense_rejected(crm, amount):
    payload = {
        "amount": amount,
        "currency": "UAH",
        "category": "api",
        "description": "Generation",
        "occurred_on": str(datetime.now(UTC).date()),
        "request_id": str(uuid.uuid4()),
    }
    assert (
        await crm.client.post("/crm/api/expenses", headers=signed(), json=payload)
    ).status_code == 422


async def test_settings_live_and_retained_on_restart(crm):
    response = await crm.client.patch(
        "/crm/api/settings",
        headers=signed(),
        json={"values": {"gift_price_stars": "77", "menu_price_uah": "450.50"}},
    )
    assert response.status_code == 200
    assert crm.settings.gift_price_stars == 77
    crm.settings.gift_price_stars = 0
    await service.load_runtime_settings(crm.factory)
    assert crm.settings.gift_price_stars == 77
    assert (
        await crm.client.patch(
            "/crm/api/settings", headers=signed(), json={"values": {"gift_price_stars": "1.1"}}
        )
    ).status_code == 422
    assert (
        await crm.client.patch(
            "/crm/api/settings", headers=signed(), json={"values": {"bot_token": "steal"}}
        )
    ).status_code == 422


async def test_credentials_encrypted_retained_and_never_returned(crm):
    payload = {
        "enabled": True,
        "config": {"ad_account_id": "act_123456"},
        "credentials": {"access_token": "secret-token-for-test"},
    }
    response = await crm.client.put("/crm/api/integrations/meta", headers=signed(), json=payload)
    assert response.status_code == 200
    assert "secret-token-for-test" not in response.text
    async with crm.factory() as session:
        row = await session.get(Integration, "meta")
        assert "secret-token-for-test" not in row.encrypted_secrets
        assert (
            security.decrypt_credentials(row.encrypted_secrets)["access_token"]
            == "secret-token-for-test"
        )
    assert (
        await crm.client.put(
            "/crm/api/integrations/meta", headers=signed(), json={**payload, "credentials": {}}
        )
    ).status_code == 200
    async with crm.factory() as session:
        row = await session.get(Integration, "meta")
        assert (
            security.decrypt_credentials(row.encrypted_secrets)["access_token"]
            == "secret-token-for-test"
        )
        log = (await session.execute(select(Audit))).scalars().all()
        assert "secret-token-for-test" not in json.dumps([row.details for row in log])


async def test_sync_never_fabricates_connected_status(crm, monkeypatch):
    await crm.client.put(
        "/crm/api/integrations/meta",
        headers=signed(),
        json={"enabled": True, "config": {"ad_account_id": "123456"}},
    )

    async def fail(*args):
        raise integrations.ProviderError("Meta: HTTP 403. Check permissions.")

    monkeypatch.setattr(integrations, "fetch_report", fail)
    response = await crm.client.post("/crm/api/integrations/meta/sync", headers=signed(), json={})
    assert response.json()["status"] == "error" and response.json()["report"] is None
    monkeypatch.setattr(
        integrations,
        "fetch_report",
        AsyncMock(return_value={"account": "Test", "campaigns": [], "currency": "UAH"}),
    )
    response = await crm.client.post("/crm/api/integrations/meta/sync", headers=signed(), json={})
    assert response.json()["status"] == "connected"


async def test_web_login_and_csrf(crm):
    login = await crm.client.post(
        "/admin/login", data={"username": "owner", "password": "password-for-test"}
    )
    assert login.status_code in (302, 303)
    assert (await crm.client.get("/crm/api/dashboard")).status_code == 200
    session = (await crm.client.get("/crm/api/session")).json()
    assert (
        await crm.client.patch("/crm/api/settings", json={"values": {"gift_price_stars": 10}})
    ).status_code == 403
    assert (
        await crm.client.patch(
            "/crm/api/settings",
            headers={"x-csrf-token": session["csrf"]},
            json={"values": {"gift_price_stars": 10}},
        )
    ).status_code == 200
    await crm.client.get("/admin/logout")
    assert (await crm.client.get("/crm/api/dashboard")).status_code == 401


async def test_export_has_bom_and_formula_protection(crm):
    await seed(crm)
    async with crm.factory() as session:
        row = await session.get(Customer, 1)
        row.name = '=HYPERLINK("https://evil")'
        await session.commit()
    response = await crm.client.get("/crm/api/export/customers", headers=signed())
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert "'=HYPERLINK" in response.text
    assert response.headers["cache-control"] == "private, no-store"


async def test_shell_does_not_include_private_data_and_assets_are_uncached(crm):
    response = await crm.client.get("/crm")
    assert response.status_code == 200 and "telegram-web-app.js" in response.text
    assert "+380000" not in response.text
    assert (await crm.client.get("/crm/static/private.txt")).status_code == 404
    assert (await crm.client.get("/crm/static/crm.js")).headers[
        "cache-control"
    ] == "private, no-store"


async def test_ledger_missing_is_reported(crm):
    result = (await crm.client.get("/crm/api/ledger", headers=signed())).json()
    assert result["available"] is False


def test_crm_url_is_derived_from_public_origin():
    assert (
        crm_url(Settings(_env_file=None, miniapp_url="https://example.org/miniapp?x=1"))
        == "https://example.org/crm"
    )
    assert not crm_url(Settings(_env_file=None, miniapp_url="http://localhost/miniapp"))


async def test_adapters_pagination_micro_units_and_no_meta_double_count():
    seen = []

    def handle(request):
        seen.append(request)
        if request.url.host == "graph.facebook.com":
            assert "secret" not in str(request.url)
            assert request.headers["authorization"] == "Bearer secret"
            if request.url.path.endswith("insights"):
                rows = [
                    {
                        "campaign_id": "1",
                        "campaign_name": "Campaign",
                        "spend": "12.50",
                        "impressions": "100",
                        "clicks": "10",
                        "actions": [
                            {"action_type": "omni_purchase", "value": "2"},
                            {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "2"},
                        ],
                    }
                ]
                return httpx.Response(
                    200,
                    json={
                        "data": rows,
                        "paging": {"cursors": {"after": "more"}, "next": "https://bad.example"}
                        if "after" not in request.url.params
                        else {},
                    },
                )
            return httpx.Response(200, json={"name": "Meta Test", "currency": "UAH"})
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "google-access"})
        body = json.loads(request.content)
        if "FROM customer" in body["query"]:
            return httpx.Response(
                200,
                json=[
                    {
                        "results": [
                            {"customer": {"descriptiveName": "Google Test", "currencyCode": "USD"}}
                        ]
                    }
                ],
            )
        assert request.headers["authorization"] == "Bearer google-access"
        return httpx.Response(
            200,
            json=[
                {
                    "results": [
                        {
                            "campaign": {"id": "2", "name": "Search"},
                            "metrics": {
                                "costMicros": "1250000",
                                "impressions": "100",
                                "clicks": "5",
                                "conversions": 1,
                            },
                        }
                    ]
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        meta = await integrations.fetch_meta(
            client,
            {"api_version": "v24.0", "ad_account_id": "1234"},
            {"access_token": "secret"},
            30,
        )
        assert len(meta["campaigns"]) == 2 and meta["campaigns"][0]["conversions"] == "2"
        google = await integrations.fetch_google(
            client,
            {"client_id": "oauth", "api_version": "v25", "customer_id": "1234567890"},
            {"client_secret": "secret", "refresh_token": "refresh"},
            30,
        )
        assert google["campaigns"][0]["spend"] == "1.25"
        assert all(request.url.host != "bad.example" for request in seen)


async def test_free_generated_gift_is_recorded_for_crm(crm, monkeypatch, tmp_path):
    mobile, desktop = tmp_path / "mobile.png", tmp_path / "desktop.png"
    job = {
        "id": "a" * 32,
        "free": True,
        "status": "generating",
        "goals": ["one"] * 5,
        "language": "ru",
        "style": "dark",
    }
    monkeypatch.setattr(api, "_read_job", lambda *args: job)
    monkeypatch.setattr(api, "_write_job", lambda *args: None)
    monkeypatch.setattr(
        api,
        "GoalScenePlanner",
        lambda settings: SimpleNamespace(
            plan=AsyncMock(return_value=SimpleNamespace(assignments=[], scenes=[], ai_cost_usd=Decimal("0.01")))
        ),
    )
    monkeypatch.setattr(
        api,
        "ReplicateVisionBoardRenderer",
        lambda **kwargs: SimpleNamespace(
            generate_goal_story=AsyncMock(return_value={"mobile": mobile, "desktop": desktop})
        ),
    )
    monkeypatch.setattr(api, "_validate_gift_files", lambda *args: None)
    monkeypatch.setattr(api, "make_preview", lambda *args: None)
    monkeypatch.setattr(api, "asyncio", SimpleNamespace(to_thread=AsyncMock()))
    await api._generate_gift(88, "a" * 32, [], None)
    async with crm.factory() as session:
        row = await session.get(WallpaperOrder, job["order_id"])
        assert row.paid and row.payment_system == "vip_bypass" and row.amount == Decimal(0)
    assert job["status"] == "ready"


async def test_empty_web_password_does_not_enable_default_login(crm):
    crm.settings.admin_password = SecretStr("")
    response = await crm.client.post(
        "/admin/login", data={"username": "admin", "password": "admin"}
    )
    assert response.status_code == 400
