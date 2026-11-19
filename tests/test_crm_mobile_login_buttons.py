"""Mobile CRM login buttons must never embed a stale one-time ticket."""
from app.bot.handlers import admin


def test_admin_main_screen_issues_ticket_on_click_not_on_render(monkeypatch):
    monkeypatch.setattr(admin, "crm_url", lambda _settings: "https://example.org/crm")
    keyboard = admin.get_admin_main_keyboard("https://example.org/crm/entry/expired")
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    crm = next(button for button in buttons if button.text == "✦ Открыть Mini CRM")
    assert crm.callback_data == "crm_secure_login"
    assert crm.web_app is None
    assert crm.url is None


def test_admin_keyboard_does_not_leak_one_time_ticket(monkeypatch):
    monkeypatch.setattr(admin, "crm_url", lambda _settings: "https://example.org/crm")
    keyboard = admin.get_admin_main_keyboard("https://example.org/crm/entry/private-token")
    assert "private-token" not in keyboard.model_dump_json()
