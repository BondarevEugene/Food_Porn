"""Join R2 object keys to durable Little Legend book ownership.

The storage browser is read-only until every deletion candidate has a
transactionally verified retention policy. Unknown objects are not safe orphans.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from app.database.session import async_session_maker
from app.little_legend.generated_art_store import illustration_key
from app.little_legend.illustration_queue_store import illustration_jobs
from app.little_legend.private_pdf_store import pdf_object_key
from app.little_legend.release_manifest_store import release_manifests
from app.little_legend.router import stories


async def associate_books(providers: list[dict]) -> dict:
    """Group object inventory by book; unlinked keys remain protected."""
    lookup: dict[str, dict] = {}
    async with async_session_maker() as session:
        jobs = (await session.execute(select(
            illustration_jobs.c.owner_id, illustration_jobs.c.story_id,
            illustration_jobs.c.job_id, illustration_jobs.c.status,
        ))).all()
        releases = (await session.execute(select(
            release_manifests.c.owner_id, release_manifests.c.story_id,
            release_manifests.c.pdf_sha256, release_manifests.c.status,
        ))).all()
        books = (await session.execute(select(
            stories.c.id, stories.c.owner_id, stories.c.created_at,
        ))).all()
    created = {(int(x.owner_id), int(x.id)): x.created_at for x in books}
    for job in jobs:
        key = illustration_key(
            owner_id=int(job.owner_id), story_id=int(job.story_id),
            job_id=job.job_id,
        )
        lookup[key] = {
            "story_id": int(job.story_id), "owner_id": int(job.owner_id),
            "status": str(job.status), "kind": "illustration",
        }
    for release in releases:
        key = pdf_object_key(
            owner_id=int(release.owner_id), story_id=int(release.story_id),
            pdf_sha256=release.pdf_sha256,
        )
        lookup[key] = {
            "story_id": int(release.story_id), "owner_id": int(release.owner_id),
            "status": str(release.status), "kind": "pdf",
        }
    grouped = defaultdict(lambda: {
        "story_id": None, "owner_id": None, "files": [],
        "used_bytes": 0, "file_count": 0, "created_at": None,
        "protected": True,
    })
    for provider in providers:
        for obj in provider["objects"]:
            ref = lookup.get(obj["key"])
            if ref is None:
                group_id = "unlinked"
            else:
                group_id = f'{ref["owner_id"]}:{ref["story_id"]}'
            row = grouped[group_id]
            if ref:
                row["story_id"] = ref["story_id"]
                row["owner_id"] = ref["owner_id"]
                timestamp = created.get((ref["owner_id"], ref["story_id"]))
                row["created_at"] = timestamp.isoformat() if timestamp else None
            row["files"].append({
                **obj, "provider": provider["provider"],
                "kind": ref["kind"] if ref else "unknown",
                "status": ref["status"] if ref else "unlinked",
                "protected": True,
            })
            row["file_count"] += 1
            row["used_bytes"] += obj["bytes"]
    result = []
    for group_id, row in grouped.items():
        result.append({"group": group_id, **row})
    return {
        "books": sorted(
            result,
            key=lambda row: row["created_at"] or "",
            reverse=True,
        ),
        "deletion_enabled": False,
        "deletion_notice": (
            "Удаление заблокировано до внедрения транзакционного реестра "
            "объектов и проверки оплаченных/активных заказов."
        ),
    }
