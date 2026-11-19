"""Connect scene-specific art briefs to the existing text-only OpenAI adapter.

No real-child photos are forwarded. This adapter does not bypass the existing
provider's opt-in settings, cost reconciliation or manual review boundaries.
"""
from __future__ import annotations

from app.little_legend.openai_illustration_provider import OpenAIIllustrationProvider
from app.little_legend.story_graph import SceneNode


class OpenAISceneArtAdapter:
    """Implements ArtProvider for the already deployed illustration provider."""

    def __init__(self, provider: OpenAIIllustrationProvider) -> None:
        self.provider = provider

    async def generate_scene(self, prompt: dict) -> bytes:
        if not isinstance(prompt, dict):
            raise ValueError("Scene prompt must be a dictionary")
        required = (
            "scene_id", "scene_order", "hero_name",
            "scene_action", "setting_and_context", "identity_anchor",
            "continuity_rules", "forbidden_inventions", "style",
        )
        if any(key not in prompt for key in required):
            raise ValueError("Incomplete scene art prompt")
        identity = prompt["identity_anchor"]
        rules = prompt["continuity_rules"]
        forbidden = prompt["forbidden_inventions"]
        if not isinstance(identity, list) or not identity:
            raise ValueError("Missing immutable hero identity")
        if not isinstance(rules, list) or not isinstance(forbidden, list):
            raise ValueError("Invalid continuity constraints")
        # The existing provider accepts at most 1200 characters of continuity.
        # Never silently truncate immutable facts or forbidden changes.
        continuity = " | ".join(str(value) for value in (*identity, *rules, *forbidden))
        if len(continuity) > 1200:
            raise ValueError("Scene continuity exceeds provider limit")
        scene = SceneNode(
            id=prompt["scene_id"],
            order=prompt["scene_order"],
            beat="opening",
            act=1,
            title=prompt.get("scene_title") or f"Сцена {prompt['scene_order']}",
            summary=prompt["setting_and_context"],
            illustration_prompt=prompt["scene_action"],
        )
        # Current provider uses scene.summary as its scene text.
        # Include the concrete action explicitly, not only background context.
        scene.summary = (
            f"Action: {prompt['scene_action']}. "
            f"Context: {prompt['setting_and_context']}"
        )
        return await self.provider.generate_scene(
            scene=scene,
            hero=prompt["hero_name"],
            style=prompt["style"],
            continuity=continuity,
        )
