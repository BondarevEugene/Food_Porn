"""Each CRM launch option gets an independent, single-use login ticket."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import admin


@pytest.mark.asyncio
async def test_crm_webapp_and_browser_use_distinct_one_time_tickets(monkeypatch):
    issue = AsyncMock(side_effect=[
        "https://example.org/crm/entry/webapp-only",
        "https://example.org/crm/entry/browser-only",
    ])
    monkeypatch.setattr(admin, "issue_crm_login_url", issue)
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )

    await admin.crm_secure_login_callback(callback)

    assert issue.await_count == 2
    keyboard = callback.message.answer.await_args.kwargs["reply_markup"]
    webapp_button = keyboard.inline_keyboard[0][0]
    browser_button = keyboard.inline_keyboard[1][0]
    assert webapp_button.web_app.url.endswith("/webapp-only")
    assert browser_button.url.endswith("/browser-only")
    assert webapp_button.web_app.url != browser_button.url
    assert callback.message.answer.await_args.kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_crm_login_refuses_to_send_same_ticket_twice(monkeypatch):
    monkeypatch.setattr(admin, "issue_crm_login_url", AsyncMock(
        return_value="https://example.org/crm/entry/same"
    ))
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    await admin.crm_secure_login_callback(callback)
    callback.message.answer.assert_not_awaited()
    assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_crm_login_does_not_issue_second_ticket_if_not_authorized(monkeypatch):
    issue = AsyncMock(return_value=None)
    monkeypatch.setattr(admin, "issue_crm_login_url", issue)
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    await admin.crm_secure_login_callback(callback)
    issue.assert_awaited_once()
    callback.message.answer.assert_not_awaited()
