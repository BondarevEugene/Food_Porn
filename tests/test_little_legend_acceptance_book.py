"""Acceptance-book smoke tests: actual PDF, offline and deterministic."""
from __future__ import annotations

import hashlib
import json
import sys
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from app.little_legend.acceptance_book import build_acceptance_book, main


def test_acceptance_book_contains_chapters_and_real_images():
    pdf, report = build_acceptance_book()
    reader = PdfReader(BytesIO(pdf), strict=True)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert report["deliverable"] is True
    assert report["print_ready"] is False
    assert report["expected_scenes"] == 3
    assert report["illustration_count"] == 3
    assert report["page_count"] == len(reader.pages)
    assert report["pdf_sha256"] == hashlib.sha256(pdf).hexdigest()
    assert "Марта" in text
    assert "волшебный сад" in text
    assert sum(bool(page.images) for page in reader.pages[2:]) >= 3
    assert report["network_used"] is False
    assert report["customer_data_used"] is False


def test_acceptance_cli_writes_pdf_and_audit(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["acceptance_book", "--output-dir", str(tmp_path)])
    assert main() == 0
    pdf = (tmp_path / "acceptance_book.pdf").read_bytes()
    report = json.loads((tmp_path / "acceptance_report.json").read_text(encoding="utf-8"))
    assert pdf.startswith(b"%PDF-")
    assert report["pdf_sha256"] == hashlib.sha256(pdf).hexdigest()
