"""
==========================================================
FOOD_PORN

Module: Prompt Builder Tests
Layer: Test

Responsibilities:
    - Verify dish names reach generated prompts
    - Verify visual and no-typography prompt constraints
==========================================================
"""

from app.database.models import ItemCategory, MenuItem
from app.services.prompt_builder import PromptBuilder


def test_prompt_is_consistent_and_has_no_text_instruction() -> None:
    item = MenuItem(
        menu_id=1,
        category=ItemCategory.MAIN,
        position=1,
        title="Pasta Carbonara",
    )
    prompt = PromptBuilder().build(item)
    assert "Pasta Carbonara" in prompt
    assert "no typography" in prompt
    assert "square composition" in prompt
