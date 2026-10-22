"""Signed Telegram identity protects gift files and administrator controls."""
import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.miniapp import api as miniapp_api
from app.miniapp.auth import verify_init_data


@pytest.mark.asyncio
@pytest.mark.parametrize("photo_count", [0, 8])
async def test_gift_api_rejects_photos_outside_one_to_seven(photo_count):
    with pytest.raises(HTTPException) as raised:
        await miniapp_api.create_gift(
            photos=[object()] * photo_count, user={"id": 23},
            goals="\n".join(f"Wish {n}" for n in range(9)))
    assert raised.value.status_code == 422


def signed_data(token="123:test", user_id=11, date=100000):
    fields = {"auth_date": str(date), "user": json.dumps({"id": user_id}), "query_id": "AA"}
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_valid_signature_and_expiration():
    raw = signed_data()
    assert verify_init_data(raw, "123:test", now=100010)["id"] == 11
    for invalid, now in ((raw.replace("11", "12"), 100010),
                         (raw, 186401), (raw + "&user=duplicate", 100010)):
        with pytest.raises(HTTPException) as exc:
            verify_init_data(invalid, "123:test", now=now)
        assert exc.value.status_code == 401


def test_api_does_not_expose_orders_or_admin_without_telegram_signature():
    with TestClient(app) as client:
        assert client.get("/miniapp").status_code == 200
        for url in ("/miniapp/api/home", "/miniapp/api/admin",
                    "/miniapp/api/gifts/" + "a" * 32 + "/files/mobile",
                    "/miniapp/api/wallpapers/1",
                    "/miniapp/api/wallpapers/1/files/mobile",
                    "/miniapp/api/menus/1/files/pdf"):
            assert client.get(url).status_code == 401
        for url in ("/miniapp/api/gifts/" + "a" * 32 + "/share",
                    "/miniapp/api/gifts/" + "a" * 32 + "/email",
                    "/miniapp/api/menus/1/checkout", "/miniapp/api/menus/1/share",
                    "/miniapp/api/menus/1/email", "/miniapp/api/wallpapers/1/email",
                    "/miniapp/api/wallpapers/1/share"):
            assert client.post(url, json={"email": "anyone@example.org"}).status_code == 401


def test_historical_wallpaper_is_owned_and_unpaid_files_remain_locked(monkeypatch):
    calls = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

    class Repository:
        def __init__(self, _session):
            pass

        async def get_for_user(self, order_id, telegram_user_id):
            calls.append((order_id, telegram_user_id))
            return None

    monkeypatch.setattr(miniapp_api, "async_session_maker", Session)
    monkeypatch.setattr(miniapp_api, "WallpaperOrderRepository", Repository)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(miniapp_api._own_wallpaper(17, 23))
    assert exc.value.status_code == 404
    assert calls == [(17, 23)]

    async def owned_order(_order_id, _user_id):
        return SimpleNamespace(paid=False, mobile_path="missing.png", desktop_path="missing.png")

    monkeypatch.setattr(miniapp_api, "_own_wallpaper", owned_order)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(miniapp_api.wallpaper_file(17, "mobile", {"id": 23}))
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        asyncio.run(miniapp_api.email_wallpaper(17, {"email": "anyone@example.org"}, {"id": 23}))
    assert exc.value.status_code == 403


def test_signed_non_admin_cannot_open_admin_or_another_users_job(monkeypatch):
    monkeypatch.setattr("app.miniapp.auth.get_settings", lambda: SimpleNamespace(bot_token="123:test"))
    with TestClient(app) as client:
        headers = {"Authorization": "tma " + signed_data(date=int(__import__("time").time()))}
        assert client.get("/miniapp/api/admin", headers=headers).status_code == 403
        assert client.get("/miniapp/api/gifts/" + "a" * 32, headers=headers).status_code == 404


def test_miniapp_assets_are_served_without_old_cached_javascript():
    with TestClient(app) as client:
        index = client.get("/miniapp")
        javascript = client.get("/miniapp/static/app.js")
        assert index.status_code == 200
        assert javascript.status_code == 200
        assert javascript.headers["cache-control"] == "no-store"
        assert "atelier4" in index.text
        assert client.get("/miniapp/static/gift-ribbon.svg").status_code == 200
        assert client.get("/miniapp/static/kitchen-cloche.svg").status_code == 200
        assert client.get("/miniapp/static/fonts/atelier-serif-bold.woff").status_code == 200
        assert client.get("/miniapp/static/fonts/other.woff").status_code == 404
