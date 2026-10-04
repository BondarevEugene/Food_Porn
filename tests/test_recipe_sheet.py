from app.render.recipes import render_recipe_sheet


def test_recipe_pdf_contains_paid_order_recipe_and_shopping_list(tmp_path):
    path = render_recipe_sheet(
        tmp_path / "recipe.pdf",
        {"Борщ": {"ingredients": ["Свёкла - 300 г"],
                   "recipe": "1. Нарезать овощи.\n2. Сварить суп."}},
        ["• Свёкла: 300 г"],
        "ru",
    )
    assert path.read_bytes().startswith(b"%PDF")
    assert path.stat().st_size > 5000
