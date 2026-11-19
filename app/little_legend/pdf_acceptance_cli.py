"""Operator-facing offline acceptance of a private Little Legend PDF.

Never prints manuscript text or PDF bytes. Exits nonzero for invalid PDFs.
The report is not a professional print certification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.little_legend.pdf_preflight import MAX_PDF_BYTES, inspect_book_pdf


def audit_file(path: Path, *, minimum_pages: int = 1) -> dict:
    if minimum_pages < 1:
        raise ValueError("minimum_pages must be positive")
    with path.open("rb") as handle:
        pdf = handle.read(MAX_PDF_BYTES + 1)
    report = inspect_book_pdf(pdf)
    issues = list(report.issues)
    if report.page_count < minimum_pages:
        issues.append("insufficient_pages")
    return {
        "valid_for_digital_review": report.valid and report.page_count >= minimum_pages,
        "print_ready": False,
        "page_count": report.page_count,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Little Legend offline PDF acceptance")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--minimum-pages", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        result = audit_file(args.pdf, minimum_pages=args.minimum_pages)
    except (OSError, ValueError) as exc:
        result = {
            "valid_for_digital_review": False,
            "print_ready": False,
            "page_count": 0,
            "issues": [type(exc).__name__],
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid_for_digital_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
