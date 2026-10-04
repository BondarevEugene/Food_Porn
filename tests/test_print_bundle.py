"""The typography package contains readable files and states its real limits."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest
from PIL import Image

from app.bot.handlers import wallpaper
from app.config import Settings
from app.services.print_bundle import create_print_bundle


def test_print_bundle_contains_poster_pdf_and_originals(tmp_path):
    mobile = tmp_path / "mobile.png"
    desktop = tmp_path / "desktop.png"
    Image.new("RGB", (540, 960), "#95725c").save(mobile)
    Image.new("RGB", (960, 540), "#95725c").save(desktop)
    archive = create_print_bundle(17, mobile, desktop, width_mm=60, height_mm=80, dpi=72)
    with ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        assert set(bundle.namelist()) == {
            "poster_60x80mm_72dpi.png", "poster_60x80mm.pdf",
            "mobile_original.png", "desktop_original.png", "PRINT_INFO.txt",
        }
        assert bundle.read("poster_60x80mm.pdf").startswith(b"%PDF")
        assert "resizing cannot create missing detail" in bundle.read("PRINT_INFO.txt").decode()
    assert create_print_bundle(17, mobile, desktop, width_mm=60, height_mm=80, dpi=72) == archive


@pytest.mark.asyncio
async def test_print_bundle_is_delivered_only_after_provider_verification(tmp_path, monkeypatch):
    mobile, desktop = tmp_path / "mobile.png", tmp_path / "desktop.png"
    for path in (mobile, desktop):
        Image.new("RGB", (120, 160), "#987654").save(path)
    order = SimpleNamespace(id=17, paid=False, amount=Decimal("17.22"),
                            mobile_path=str(mobile), desktop_path=str(desktop))
    delivered = []

    class Repo:
        def __init__(self, session):
            pass

        async def get_for_user(self, order_id, user_id):
            assert order_id == 17 and user_id == 42
            return order

        async def mark_paid(self, record, payment_id):
            record.paid = True

    class SessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return False

    class Provider:
        result = None

        def __init__(self, settings):
            pass

        async def verify_portmone_payment(self, order_id, amount, product):
            assert (order_id, amount, product) == (17, Decimal("17.22"), "wallpaper")
            return self.result

    async def send_files(*args):
        delivered.append("images")

    def make_archive(*args, **kwargs):
        delivered.append("archive")
        return tmp_path / "dummy.zip"

    monkeypatch.setattr(wallpaper, "WallpaperOrderRepository", Repo)
    monkeypatch.setattr(wallpaper, "PaymentService", Provider)
    monkeypatch.setattr(wallpaper, "_send_full", send_files)
    monkeypatch.setattr(wallpaper, "create_print_bundle", make_archive)
    message = SimpleNamespace(answer_document=AsyncMock(), answer=AsyncMock())
    callback = SimpleNamespace(data="check_pay_17", from_user=SimpleNamespace(id=42, language_code="ru"),
                               message=message, answer=AsyncMock())
    state = SimpleNamespace(get_data=AsyncMock(return_value={"ui_lang": "ru"}))
    settings = Settings(_env_file=None)
    await wallpaper.verify_wallpaper_payment(callback, settings, SessionFactory(), state)
    assert delivered == [] and not order.paid
    Provider.result = SimpleNamespace(payment_id="verified17")
    await wallpaper.verify_wallpaper_payment(callback, settings, SessionFactory(), state)
    assert delivered == ["images", "archive"] and order.paid
    message.answer_document.assert_awaited_once()
