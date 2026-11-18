"""Validated request for rendering an illustrated Little Legend book.

Image bytes are supplied by the authenticated story owner, never fetched from URLs.
"""
from __future__ import annotations

import base64
import binascii

from pydantic import BaseModel, Field, model_validator

from app.little_legend.illustrated_pdf import MAX_IMAGE_BYTES


class IllustratedBookRequest(BaseModel):
    illustrations: dict[str, str] = Field(min_length=1, max_length=40)
    approved_scene_ids: set[str] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def matching_approvals(self) -> "IllustratedBookRequest":
        if set(self.illustrations) != self.approved_scene_ids:
            raise ValueError("Every supplied scene must be explicitly approved")
        return self

    def decoded_images(self) -> dict[str, bytes]:
        decoded = {}
        for scene_id, encoded in self.illustrations.items():
            if len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4 + 4:
                raise ValueError("Illustration is oversized")
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("Invalid base64 illustration") from exc
            if not raw or len(raw) > MAX_IMAGE_BYTES:
                raise ValueError("Illustration is missing or oversized")
            decoded[scene_id] = raw
        return decoded
