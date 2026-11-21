"""Durable write-and-register boundary for private Little Legend artifacts.

A successful S3 write is never rolled back by deleting customer content.
If Neon fails, the object remains private and the operation reports failure.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from app.crm.storage_artifacts import register
from app.database.session import async_session_maker
from app.little_legend.generated_art_store import (
    GeneratedArtStore,
    illustration_key,
    validate_generated_art,
)
from app.little_legend.private_pdf_store import (
    PrivatePDFStore,
    pdf_object_key,
    validate_pdf,
)


@dataclass(frozen=True)
class RegisteredObject:
    artifact_id: int
    key: str


class PdfWriter(PrivatePDFStore, Protocol):
    pass


async def register_release_pdf(
    *,
    store: PdfWriter,
    bucket: str,
    owner_id: int,
    story_id: int,
    pdf: bytes,
    pdf_sha256: str,
) -> RegisteredObject:
    """Write verified PDF, then commit protected metadata before success."""
    validate_pdf(pdf, expected_sha256=pdf_sha256)
    if not bucket:
        raise ValueError("Bucket is required")
    key = pdf_object_key(
        owner_id=owner_id, story_id=story_id, pdf_sha256=pdf_sha256,
    )
    await asyncio.to_thread(store.put, key=key, data=pdf, content_type="application/pdf")
    async with async_session_maker() as session:
        artifact_id = await register(
            session, bot_id="little_legend", connection="release",
            bucket=bucket, object_key=key, order_type="story",
            order_id=str(story_id), kind="sealed_pdf",
            bytes_count=len(pdf), etag=pdf_sha256,
        )
        await session.commit()
    return RegisteredObject(artifact_id=artifact_id, key=key)


async def register_generated_illustration(
    *,
    store: GeneratedArtStore,
    bucket: str,
    owner_id: int,
    story_id: int,
    job_id: str,
    image: bytes,
) -> RegisteredObject:
    """Write sanitized JPEG and persist protected metadata."""
    validate_generated_art(image)
    if not bucket:
        raise ValueError("Bucket is required")
    key = illustration_key(
        owner_id=owner_id, story_id=story_id, job_id=job_id,
    )
    await asyncio.to_thread(store.put, key=key, data=image, content_type="image/jpeg")
    async with async_session_maker() as session:
        artifact_id = await register(
            session, bot_id="little_legend", connection="illustrations",
            bucket=bucket, object_key=key, order_type="story",
            order_id=str(story_id), kind="generated_illustration",
            bytes_count=len(image),
        )
        await session.commit()
    return RegisteredObject(artifact_id=artifact_id, key=key)
