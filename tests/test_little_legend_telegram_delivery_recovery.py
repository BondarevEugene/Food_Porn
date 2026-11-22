"""Telegram recovery: owner-only, confirmed effects, no PDF resend."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.bot.handlers.little_legend_release_preflight import (
    reconcile_delivery_callback,
    release_actions,
)
from app.little_legend.book_delivery import DeliveryStatus
from app.little_legend.delivery_reconciliation import (
    DeliveryDiagnosis,
    RecoveryAction,
)


def _callback(owner=42, chat=42, story=17):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=owner),
        message=SimpleNamespace(
            chat=SimpleNamespace(id=chat, type="private"),
            answer=AsyncMock(),
        ),
        data=f"ll_delivery_reconcile:{story}",
        answer=AsyncMock(),
    )


def test_recovery_button_only_for_confirmed_projection_gap():
    for action in RecoveryAction:
        keyboard = release_actions(
            17, ready_for_export=False,
            delivery_status=DeliveryStatus.UNCERTAIN,
            recovery_action=action,
        )
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        ]
        assert ("ll_delivery_reconcile:17" in callbacks) is (
            action == RecoveryAction.REPAIR_PROJECTION
        )
        assert "ll_send:17" not in callbacks


@pytest.mark.asyncio
async def test_confirmed_delivery_can_be_repaired_without_resend():
    callback = _callback()
    diagnosis = DeliveryDiagnosis(
        owner_id=42, story_id=17, action=RecoveryAction.CONSISTENT,
        effect_status=None, manifest_status=DeliveryStatus.SENT,
        telegram_message_id=123,
    )
    with patch(
        "app.bot.handlers.little_legend_release_preflight.repair_confirmed_projection",
        new_callable=AsyncMock, return_value=diagnosis,
    ) as repair:
        await reconcile_delivery_callback(callback)
    repair.assert_awaited_once_with(owner_id=42, story_id=17)
    callback.answer.assert_awaited_once()
    callback.message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_foreign_chat_cannot_repair_delivery():
    callback = _callback(chat=99)
    with patch(
        "app.bot.handlers.little_legend_release_preflight.repair_confirmed_projection",
        new_callable=AsyncMock,
    ) as repair:
        await reconcile_delivery_callback(callback)
    repair.assert_not_awaited()
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_unconfirmed_delivery_does_not_claim_success():
    callback = _callback()
    diagnosis = DeliveryDiagnosis(
        owner_id=42, story_id=17, action=RecoveryAction.MANUAL_REVIEW,
        effect_status=None, manifest_status=DeliveryStatus.UNCERTAIN,
    )
    with patch(
        "app.bot.handlers.little_legend_release_preflight.repair_confirmed_projection",
        new_callable=AsyncMock, return_value=diagnosis,
    ):
        await reconcile_delivery_callback(callback)
    assert "Нужна проверка" in callback.answer.await_args.args[0]
