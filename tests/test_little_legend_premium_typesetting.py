"""Editorial typesetting must preserve every word in scene prose."""
import pytest

from app.little_legend.illustrated_pdf import _editorial_paragraphs


def test_short_paragraphs_and_line_breaks_are_preserved():
    assert _editorial_paragraphs("Первый абзац.\n\nВторой абзац.") == [
        "Первый абзац.", "Второй абзац.",
    ]


def test_long_scene_splits_only_on_sentence_boundaries():
    original = " ".join(
        f"Герой отправился в путешествие номер {index}."
        for index in range(25)
    )
    parts = _editorial_paragraphs(original, max_chars=120)
    assert len(parts) > 1
    assert " ".join(parts) == original
    assert all(part.endswith(".") for part in parts)


def test_crlf_normalization_preserves_content():
    assert _editorial_paragraphs("Начало.\r\nПродолжение.") == [
        "Начало.", "Продолжение.",
    ]


def test_invalid_paragraph_limit_is_rejected():
    with pytest.raises(ValueError, match="at least 100"):
        _editorial_paragraphs("Текст.", max_chars=50)
