"""Guard deliverable completeness and email attachments."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.config import Settings
from app.database.models import GenerationStatus
from app.services import email_service
from app.services.menu_quality import validate_menu_artwork, validate_menu_files


def test_quality_rejects_duplicate_dishes_and_missing_recipes(tmp_path: Path) -> None:
    one = tmp_path / "one.jpg"
    Image.new("RGB", (1024, 1024), "#7d6854").save(one)
    items = [SimpleNamespace(title=title, image_path=str(one),
                             generation_status=GenerationStatus.DONE)
             for title in ("Окрошка", "Вареники")]
    menu = SimpleNamespace(items=items)
    with pytest.raises(ValueError, match="Duplicate"):
        validate_menu_artwork(menu, tmp_path / "absent.jpg")
    pdf = tmp_path / "output.pdf"
    pdf.write_bytes(b"%PDF-" + b"0" * 1500)
    with pytest.raises(ValueError, match="Recipes"):
        validate_menu_files(menu, (pdf,), {"Окрошка": {}})


@pytest.mark.asyncio
async def test_email_contains_all_requested_files(monkeypatch, tmp_path: Path) -> None:
    pdf = tmp_path / "menu.pdf"
    recipes = tmp_path / "recipes.pdf"
    pdf.write_bytes(b"%PDF-" + b"a" * 1000)
    recipes.write_bytes(b"%PDF-" + b"b" * 1000)
    settings = Settings(_env_file=None, smtp_host="smtp.example.org", smtp_port=465,
                        smtp_user="atelier@example.org", smtp_password="secret")
    monkeypatch.setattr(email_service, "get_settings", lambda: settings)
    sent = []
    async def capture(message, **kwargs):
        sent.append(message)
    monkeypatch.setattr(email_service.aiosmtplib, "send", capture)
    await email_service.send_ready_order_email("guest@example.org", "Ваш заказ", [pdf, recipes])
    assert len(sent) == 1
    assert [part.get_filename() for part in sent[0].iter_attachments()] == ["menu.pdf", "recipes.pdf"]
    with pytest.raises(ValueError):
        email_service.normalize_recipient("attacker@example.org\r\nBCC:someone@example.org")
