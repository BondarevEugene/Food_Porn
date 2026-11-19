"""Offline release acceptance and private generated-art configuration tests."""
from io import BytesIO
from unittest.mock import patch

import pytest
from reportlab.lib.pagesizes import A5
from reportlab.pdfgen import canvas

from app.little_legend.art_storage_config import configured_generated_art_store
from app.little_legend.pdf_acceptance_cli import audit_file, main


def make_pdf() -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A5)
    pdf.drawString(40, 400, "EDITORIAL PROOF")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_offline_acceptance_reports_valid_editorial_pdf(tmp_path):
    path = tmp_path / "book.pdf"
    path.write_bytes(make_pdf())
    result = audit_file(path)
    assert result["valid_for_digital_review"]
    assert result["print_ready"] is False
    assert result["page_count"] == 1
    assert "editorial_proof_only" in result["issues"]


def test_offline_acceptance_rejects_short_book(tmp_path):
    path = tmp_path / "book.pdf"
    path.write_bytes(make_pdf())
    result = audit_file(path, minimum_pages=4)
    assert not result["valid_for_digital_review"]
    assert "insufficient_pages" in result["issues"]
    assert main([str(path), "--minimum-pages", "4"]) == 1


def test_offline_acceptance_rejects_corrupt_pdf(tmp_path):
    path = tmp_path / "book.pdf"
    path.write_bytes(b"%PDF-broken")
    assert main([str(path)]) == 1


def test_generated_art_store_requires_private_configuration(monkeypatch):
    for name in (
        "LITTLE_LEGEND_S3_ENDPOINT_URL",
        "LITTLE_LEGEND_S3_BUCKET",
        "LITTLE_LEGEND_S3_REGION",
        "LITTLE_LEGEND_S3_ACCESS_KEY_ID",
        "LITTLE_LEGEND_S3_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="not configured"):
        configured_generated_art_store()


def test_generated_art_store_uses_private_s3_settings(monkeypatch):
    values = {
        "LITTLE_LEGEND_S3_ENDPOINT_URL": "https://storage.example.test",
        "LITTLE_LEGEND_S3_BUCKET": "private",
        "LITTLE_LEGEND_S3_REGION": "eu-central-1",
        "LITTLE_LEGEND_S3_ACCESS_KEY_ID": "access",
        "LITTLE_LEGEND_S3_SECRET_ACCESS_KEY": "secret",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    with patch("app.little_legend.art_storage_config.S3GeneratedArtStore") as factory:
        configured_generated_art_store()
    settings = factory.call_args.args[0]
    assert settings.bucket == "private"
    assert settings.endpoint_url.startswith("https://")
