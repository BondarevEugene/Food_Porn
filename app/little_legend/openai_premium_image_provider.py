"""Opt-in OpenAI Images edit adapter for Little Legend premium illustrations.

Uses the child's authorized in-memory JPEG as image input, not a text-only
identity description. Never logs or persists the input photo or API key.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass

import httpx

from app.little_legend.illustration_provider_receipts import IllustrationProviderResult
from app.little_legend.premium_batch_manifest import PremiumArtRequest
from app.little_legend.premium_private_reference import PrivatePremiumReference
from app.little_legend.premium_visual_contract import BookVisualPlan


@dataclass(frozen=True)
class OpenAIPremiumImageSettings:
    api_key: str
    model: str = "gpt-image-1"
    timeout_seconds: float = 180.0

    def __post_init__(self) -> None:
        if not self.api_key.strip() or not 10 <= self.timeout_seconds <= 300:
            raise ValueError("Premium image provider is not configured")


class OpenAIPremiumImageProvider:
    def __init__(self, settings: OpenAIPremiumImageSettings) -> None:
        self._settings = settings

    async def generate_premium_image(
        self, *, request: PremiumArtRequest, plan: BookVisualPlan,
        reference: PrivatePremiumReference,
    ) -> IllustrationProviderResult:
        if request.reference_id != reference.reference_id:
            raise PermissionError("Reference identity mismatch")
        if not reference.image_jpeg.startswith(bytes((255, 216, 255))):
            raise ValueError("Identity reference must be sanitized JPEG")
        prompt = (
            "Create one premium illustrated children's storybook scene. "
            "Use the attached private child portrait only as an identity "
            "reference for the protagonist; do not paste the photograph, "
            "make a collage, or repeat the same pose. "
            "Keep the entire head visible with safe margins, no text, "
            "no watermark. Preserve consistent recognizable facial traits. "
            f"Genre: {plan.genre.value}. "
            f"Scene: {request.scene_description}. "
            f"Costume: {request.costume_direction}. "
            f"Environment: {request.background_direction}."
        )
        async with httpx.AsyncClient(
            timeout=self._settings.timeout_seconds,
        ) as client:
            response = await client.post(
                "https://api.openai.com/v1/images/edits",
                headers={
                    "Authorization": f"Bearer {self._settings.api_key}",
                },
                data={
                    "model": self._settings.model,
                    "prompt": prompt,
                    "size": "1536x1024",
                },
                files={
                    "image": (
                        "identity.jpg", reference.image_jpeg, "image/jpeg",
                    ),
                },
            )
            response.raise_for_status()
            payload = response.json()
        images = payload.get("data")
        if not isinstance(images, list) or len(images) != 1:
            raise ValueError("Image provider returned no unique image")
        encoded = images[0].get("b64_json")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("Image provider returned no image bytes")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Image provider returned invalid image bytes") from exc
        return IllustrationProviderResult(image=data)
