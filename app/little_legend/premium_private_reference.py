"""Private, per-job identity reference handoff to the premium image provider.

References are resolved before any billable dispatch. Bytes exist only in
memory; never put them in job payloads, logs or provider receipts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.little_legend.image_safety import sanitize_image
from app.little_legend.premium_batch_manifest import PremiumArtRequest


class PrivateReferenceReader(Protocol):
    async def read_reference(
        self, *, owner_id: int, story_id: int, reference_id: str,
    ) -> bytes: ...


@dataclass(frozen=True)
class PrivatePremiumReference:
    reference_id: str
    image_jpeg: bytes


async def load_private_premium_reference(
    *, reader: PrivateReferenceReader,
    owner_id: int,
    story_id: int,
    request: PremiumArtRequest,
) -> PrivatePremiumReference:
    """Fetch one authorized identity reference and strip image metadata."""
    if owner_id <= 0 or story_id <= 0 or not request.reference_id.strip():
        raise PermissionError("Invalid private reference identity")
    raw = await reader.read_reference(
        owner_id=owner_id, story_id=story_id,
        reference_id=request.reference_id,
    )
    sanitized = sanitize_image(raw)
    return PrivatePremiumReference(
        reference_id=request.reference_id, image_jpeg=sanitized.data,
    )
