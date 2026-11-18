"""Parent sketches must be preserved without fictional child facts."""
import pytest
from pydantic import ValidationError

from app.little_legend.client_sketch import ParentSketch, outline_from_sketch


def sketch(**overrides):
    return ParentSketch(**({
        "premise": "Марта находит карту в старой библиотеке.",
        "moments": ["Марта встречает сову.", "Сова показывает ключ."],
        "wish": "Найти тайную комнату",
        "special_choice": "Марта решает поделиться ключом",
        "ending": "Все возвращаются домой",
    } | overrides))


def test_parent_ideas_are_preserved_and_ordered():
    outline = outline_from_sketch(sketch(), chapter_count=6)
    text = " ".join(node.summary for node in outline.graph.nodes)
    assert "Марта встречает сову." in text
    assert "Сова показывает ключ." in text
    assert text.index("Марта встречает сову.") < text.index("Сова показывает ключ.")
    assert outline.design.decisive_choice == "Марта решает поделиться ключом"
    assert outline.ai_generated is False


def test_missing_details_become_questions_not_invented_facts():
    outline = outline_from_sketch(
        sketch(wish="", special_choice="", ending="", moments=["Марта ищет книгу."]),
        chapter_count=5,
    )
    assert any("решающий выбор" in question for question in outline.unresolved_questions)
    assert outline.graph.nodes[-1].summary == ""
    assert outline.source_only


def test_too_many_moments_are_not_silently_dropped():
    with pytest.raises(ValueError, match="Too many"):
        outline_from_sketch(
            sketch(moments=[f"Событие {i}" for i in range(8)]),
            chapter_count=3,
        )


def test_empty_moments_rejected():
    with pytest.raises(ValidationError):
        sketch(moments=["  "])
