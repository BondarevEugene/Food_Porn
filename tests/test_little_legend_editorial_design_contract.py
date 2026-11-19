"""Editorial design tokens are intentionally stable and reviewable.

This is a visual polish pass, not a claim of press-ready certification.
"""
from app.little_legend import illustrated_pdf


def test_editorial_layout_retains_proof_disclosure() -> None:
    import inspect

    source = inspect.getsource(illustrated_pdf.render_illustrated_proof)
    assert "EDITORIAL PROOF" in source
    assert "НЕ ДЛЯ ТИПОГРАФИИ" in source


def test_editorial_layout_has_typographic_hierarchy() -> None:
    import inspect

    source = inspect.getsource(illustrated_pdf.render_illustrated_proof)
    assert "fontSize=25" in source
    assert "fontSize=16" in source
    assert "fontSize=10.5" in source
