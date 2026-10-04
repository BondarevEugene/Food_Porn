"""Contact detection, ownership and explicit language switching."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import start
from app.database.models import Language


class State:
    def __init__(self, **data):
        self.data = data

    async def get_data(self):
        return self.data

    async def update_data(self, **items):
        self.data.update(items)


class Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_contact_language_and_owner_validation(monkeypatch):
    registered = []

    class Repo:
        def __init__(self, session):
            pass

        async def register(self, **items):
            registered.append(items)

    monkeypatch.setattr(start, "async_session_maker", lambda: Session())
    monkeypatch.setattr(start, "CustomerRepository", Repo)
    user = SimpleNamespace(id=42, full_name="Person", language_code="en")
    message = SimpleNamespace(from_user=user,
                              contact=SimpleNamespace(user_id=77, phone_number="+71234567890"),
                              answer=AsyncMock())
    state = State(ui_lang="en", lang_selected=False)
    await start.receive_contact(message, state)
    assert registered == []
    message.contact.user_id = 42
    await start.receive_contact(message, state)
    assert registered[-1]["language"] == Language.RU
    assert state.data["ui_lang"] == "ru"
    message.contact.phone_number = "+380501234567"
    state.data.update(ui_lang="ru", lang_selected=True)
    await start.receive_contact(message, state)
    assert registered[-1]["language"] == Language.RU
