"""Telegram release UI must never offer a duplicate dispatch."""
from app.bot.handlers.little_legend_release_preflight import release_actions
from app.little_legend.book_delivery import DeliveryStatus


def _callbacks(ready, status):
    return [
        button.callback_data
        for row in release_actions(
            42, ready_for_export=ready, delivery_status=status,
        ).inline_keyboard
        for button in row
    ]


def test_unready_book_cannot_prepare_or_send():
    actions = _callbacks(False, None)
    assert "ll_prepare:42" not in actions
    assert "ll_send:42" not in actions


def test_ready_book_can_prepare_but_not_send():
    actions = _callbacks(True, None)
    assert "ll_prepare:42" in actions
    assert "ll_send:42" not in actions


def test_sealed_book_can_send_but_not_reassemble():
    actions = _callbacks(False, DeliveryStatus.READY)
    assert "ll_send:42" in actions
    assert "ll_prepare:42" not in actions


def test_ambiguous_or_completed_delivery_cannot_repeat():
    for status in (DeliveryStatus.SENDING, DeliveryStatus.UNCERTAIN, DeliveryStatus.SENT):
        actions = _callbacks(True, status)
        assert "ll_prepare:42" not in actions
        assert "ll_send:42" not in actions
