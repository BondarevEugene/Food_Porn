from app.services.menu_art_directions import DIRECTIONS, choose_direction


def test_fifty_distinct_directions_with_theme_counts():
    assert len(DIRECTIONS) == 50
    assert len({item.code for item in DIRECTIONS}) == 50
    assert [sum(item.theme == theme for item in DIRECTIONS) for theme in ("light", "dark", "color")] == [15, 15, 20]


def test_seed_is_reproducible_and_stays_within_theme():
    for theme in ("light", "dark", "color"):
        first = choose_direction(theme, "order-123")
        assert first == choose_direction(theme, "order-123")
        assert first.theme == theme


def test_prompt_reserves_portrait_and_typography():
    prompt = choose_direction("dark", 123).prompt().lower()
    assert "no text" in prompt
    assert "no faces" in prompt
    assert "original customer photographs" in prompt
