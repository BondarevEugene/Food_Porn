"""
==========================================================
FOOD_PORN & OLD MONEY MANIFESTATIONS
Module: Structured JSON Prompt Architect
==========================================================
"""



class PromptArchitect:
    """
    Трансформирует пользовательские цели и фото в структурированный
    JSON-сценарий vision board, а затем компилирует его в мега-промпт для AI.
    """

    @staticmethod
    def build_structured_blueprint(goals: list[str], photo_count: int) -> dict:
        goals_text = "; ".join(goals)

        blueprint = {
            "project": "Seamless Luxury Vision Board Collage - Single Character Consistency",
            "canvas": {
                "aspect_ratio": "9:16",
                "style": "photorealistic seamless double-exposure composite, soft ethereal blending, light leaks, "
                         "warm bokeh particles, gold aura glow",
                "color_palette": {
                    "primary": ["#D4AF37", "#F5E6D3", "#2C1E14"],
                    "tone": "warm golden amber, luxury aesthetic"
                },
                "typography_style": "elegant classical serif, gold and ivory color, subtle drop shadow, atmospheric "
                                    "placement"
            },
            "character_consistency_rule": {
                "main_subject_id": "SUBJECT_01",
                "instruction": f"Maintain 100% facial identity, body proportions, and features of SUBJECT_01 across all {photo_count} photo blocks based on the provided reference collage.",
                "character_profile": {
                    "facial_identity": "Same person across all blocks (face anchor from reference)",
                    "style": "Elegant, luxury, polished Old Money aesthetic"
                }
            },
            "central_element": {
                "type": "main_portrait",
                "subject": "SUBJECT_01",
                "pose_and_framing": "Close-up front-facing portrait, warm inviting smile, subtle luxury attire, "
                                    "soft golden lighting",
                "integration_effect": "Seamless feathered soft edges blending into the background fog"
            },
            "user_custom_goals_integration": {
                "extracted_goals": goals,
                "instruction": f"Seamlessly integrate visual representations of these specific user goals into the "
                               f"collage layout: {goals_text}"
            },
            "blending_instructions": {
                "transitions": "Fully seamless double-exposure style transitions between all panels, no hard photo "
                               "borders",
                "lighting": "Unified golden glow, subtle lens flares, and soft bokeh light spots across the whole "
                            "canvas"
            }
        }
        return blueprint

    @classmethod
    def compile_to_prompt(cls, goals: list[str], photo_count: int) -> str:
        """
        Компилирует структурированный шаблон в мощный финальный промпт для модели генерации.
        """
        blueprint = cls.build_structured_blueprint(goals, photo_count)

        # Превращаем структуру в плотный, понятный для LLM/Image-модели промпт с сохранением структуры
        prompt = (
            f"Create a high-end luxury fine art vision board collage with strict 9:16 vertical layout, "
            f"photorealistic seamless double-exposure composite, soft ethereal blending, light leaks, warm bokeh "
            f"particles, gold aura glow."
            f"Color palette: warm golden amber, #D4AF37 gold, #F5E6D3 ivory, #2C1E14 deep brown. "
            f"Character consistency: maintain 100% facial identity of SUBJECT_01 from the reference image across all "
            f"blocks."
            f"Incorporate these specific user manifestation goals seamlessly: {', '.join(goals)}. "
            f"Add elegant classical serif gold typography for affirmations where appropriate. "
            f"Unified cinematic Vogue editorial lighting, absolute masterpiece."
        )
        return prompt
