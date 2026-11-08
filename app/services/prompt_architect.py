"""
FOOD_PORN & OLD MONEY MANIFESTATIONS
Module: Structured JSON Prompt Architect
"""

import json


class PromptArchitect:
    """Build a structured vision-board specification and compile it into a prompt."""

    @staticmethod
    def build_structured_blueprint(
        goals: list[str],
        photo_count: int,
    ) -> dict:
        """Create the structured specification for the vision-board image."""
        goals_text = "; ".join(goals)

        return {
            "project": ("Seamless Luxury Vision Board Collage - Single Character Consistency"),
            "canvas": {
                "aspect_ratio": "9:16",
                "style": (
                    "photorealistic seamless double-exposure composite, "
                    "soft ethereal blending, light leaks, warm bokeh particles, "
                    "gold aura glow"
                ),
                "color_palette": {
                    "primary": ["#D4AF37", "#F5E6D3", "#2C1E14"],
                    "tone": "warm golden amber, luxury aesthetic",
                },
                "typography_style": (
                    "elegant classical serif, gold and ivory color, "
                    "subtle drop shadow, atmospheric placement"
                ),
            },
            "character_consistency_rule": {
                "main_subject_id": "SUBJECT_01",
                "instruction": (
                    "Maintain consistent facial identity, body proportions, "
                    f"and features of SUBJECT_01 across all {photo_count} "
                    "photo blocks, based on the provided reference images."
                ),
                "character_profile": {
                    "facial_identity": (
                        "Same person across all blocks; use the reference "
                        "images to preserve identity."
                    ),
                    "style": "Elegant, luxury, polished Old Money aesthetic",
                },
            },
            "central_element": {
                "type": "main_portrait",
                "subject": "SUBJECT_01",
                "pose_and_framing": (
                    "Close-up front-facing portrait, warm inviting smile, "
                    "subtle luxury attire, soft golden lighting"
                ),
                "integration_effect": (
                    "Seamless feathered soft edges blending into the background fog"
                ),
            },
            "user_custom_goals_integration": {
                "extracted_goals": goals,
                "instruction": (
                    "Seamlessly integrate visual representations of these "
                    f"specific user goals into the collage layout: {goals_text}"
                ),
            },
            "blending_instructions": {
                "transitions": (
                    "Fully seamless double-exposure transitions between "
                    "all panels, without hard photo borders"
                ),
                "lighting": (
                    "Unified golden glow, subtle lens flares, and soft "
                    "bokeh light spots across the whole canvas"
                ),
            },
        }

    @classmethod
    def compile_to_prompt(
        cls,
        goals: list[str],
        photo_count: int,
    ) -> str:
        """Compile the structured specification into an image-generation prompt."""
        blueprint = cls.build_structured_blueprint(goals, photo_count)
        blueprint_json = json.dumps(
            blueprint,
            ensure_ascii=False,
            indent=2,
        )

        return (
            "Create a high-end luxury fine-art vision board collage. "
            "Use the following structured specification as the creative brief. "
            "Preserve the user's goals, reference-person identity, composition, "
            "lighting, typography, and blending instructions. "
            "Render a seamless, photorealistic vertical 9:16 composition. "
            "Do not add hard panel borders or place decorative text over "
            "the subject's face. Treat the JSON as instructions for the image, "
            "not as text to render into the image.\n\n"
            "STRUCTURED CREATIVE BRIEF:\n"
            f"{blueprint_json}"
        )
