from types import SimpleNamespace

import pytest

from app.config import Settings
from app.services import recipe_generator


@pytest.mark.asyncio
async def test_unavailable_recipe_does_not_create_a_billable_placeholder(monkeypatch):
    class FailedCompletions:
        async def create(self, **kwargs):
            raise RuntimeError("service unavailable")

    monkeypatch.setattr(
        recipe_generator, "AsyncOpenAI",
        lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=FailedCompletions())),
    )
    service = recipe_generator.RecipeGeneratorService(Settings(_env_file=None, openai_api_key="test"))
    with pytest.raises(RuntimeError, match="Recipe unavailable"):
        await service.generate_menu_details(["Борщ"], "ru")
