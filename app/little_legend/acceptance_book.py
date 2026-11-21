"""Offline Little Legend acceptance book: no customers, payments, AI or network.

Usage: python -m app.little_legend.acceptance_book --output-dir /tmp/legend-acceptance
Produces a real PDF using the production renderer plus a JSON release audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from app.little_legend.illustrated_pdf import render_illustrated_proof
from app.little_legend.release_quality_engine import audit_book_release
from app.little_legend.story_graph import build_graph
from app.little_legend.story_writer import ChapterDraft, StoryManuscript


def _art(index: int) -> bytes:
    """Deterministic, clearly synthetic artwork; not a generated customer image."""
    palettes = [
        ("#e8dafa", "#775ab3", "#fff5cf"),
        ("#d4f1ed", "#247c84", "#f9d9a8"),
        ("#fbe1d8", "#c05d72", "#d7d9fa"),
    ]
    background, foreground, accent = palettes[index % len(palettes)]
    picture = Image.new("RGB", (900, 900), background)
    draw = ImageDraw.Draw(picture)
    draw.ellipse((95, 110, 800, 815), fill=accent)
    draw.polygon([(450, 125), (755, 640), (155, 640)], fill=foreground)
    draw.ellipse((355, 340, 545, 530), fill=background)
    output = BytesIO()
    picture.save(output, format="PNG")
    return output.getvalue()


def build_acceptance_book() -> tuple[bytes, dict]:
    """Build a complete approved synthetic three-scene book and audit it."""
    graph = build_graph([
        "Марта находит карту волшебного сада.",
        "Марта помогает потерявшейся птице.",
        "Марта возвращает свет в сад.",
    ])
    manuscript = StoryManuscript(
        hero_name="Марта", parent_approved=True,
        chapters=[
            ChapterDraft(
                scene_id=node.id, approved=True,
                text=(
                    "Марта открыла старую карту и увидела тропинку к волшебному саду. "
                    "Она внимательно посмотрела вокруг и решила помочь друзьям. "
                    "Вместе они нашли дорогу и вернули свет в сказочный мир. "
                ) * 4,
            )
            for node in graph.nodes
        ],
    )
    images = {node.id: _art(i) for i, node in enumerate(graph.nodes)}
    pdf = render_illustrated_proof(
        title="Марта и волшебный сад", dedication="Для всех маленьких исследователей",
        graph=graph, manuscript=manuscript, illustrations=images,
        approved_scene_ids=set(images), edition="digital", palette="lavender",
    )
    audit = audit_book_release(
        pdf=pdf, illustrations=images, expected_scenes=len(images),
        edition="digital", cover_scene_id=graph.nodes[0].id,
    )
    report = audit.model_dump(mode="json")
    report.update({
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "pdf_bytes": len(pdf),
        "synthetic_fixture": True,
        "network_used": False,
        "customer_data_used": False,
        "ai_used": False,
        "print_certified": False,
    })
    if not audit.deliverable:
        raise ValueError("Acceptance book failed release audit: " + ",".join(audit.issue_codes))
    return pdf, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/little_legend_acceptance"))
    args = parser.parse_args()
    pdf, report = build_acceptance_book()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    (output / "acceptance_book.pdf").write_bytes(pdf)
    (output / "acceptance_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"ACCEPTANCE_OK pages={report['page_count']} sha256={report['pdf_sha256']}")
    print(f"PDF: {output / 'acceptance_book.pdf'}")
    print(f"REPORT: {output / 'acceptance_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
