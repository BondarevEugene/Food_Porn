"""Контракт відеозамовлення не успадковує оплату карти бажань."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.video_order_contract import VideoOrderContract, VideoOrderStatus


def make_order(**overrides):
    fields = dict(
        order_id=3,
        wallpaper_order_id=2,
        owner_telegram_id=123,
        amount=Decimal("99.00"),
    )
    fields.update(overrides)
    return VideoOrderContract(**fields)


def test_video_starts_unpaid_with_cinematic_music_and_no_voice():
    order = make_order()
    assert order.status == VideoOrderStatus.WAITING_FOR_PAYMENT
    assert (order.music_mode, order.music_mood, order.ai_voice) == (
        "auto", "cinematic", False
    )
    assert not order.can_download(123)


def test_wallpaper_payment_does_not_unlock_video():
    order = make_order()
    assert not order.can_download(123)
    with pytest.raises(ValueError):
        order.transition(VideoOrderStatus.QUEUED)


def test_paid_state_requires_its_own_payment_evidence():
    with pytest.raises(ValidationError):
        make_order(status=VideoOrderStatus.PAID)
    with pytest.raises(ValidationError):
        make_order(status=VideoOrderStatus.PAID, payment_reference="payment-1")


def test_only_owner_can_download_completed_video():
    order = make_order(
        status=VideoOrderStatus.PAID,
        payment_reference="verified-video-payment",
        paid_at=datetime.now(UTC),
    )
    order = order.transition(VideoOrderStatus.QUEUED)
    order = order.transition(VideoOrderStatus.PROCESSING)
    order = order.transition(VideoOrderStatus.READY)
    assert order.can_download(123)
    assert not order.can_download(999)
    assert order.transition(VideoOrderStatus.READY) == order


def test_invalid_transition_and_refund_block_download():
    order = make_order(
        status=VideoOrderStatus.READY,
        payment_reference="verified-video-payment",
        paid_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError):
        order.transition(VideoOrderStatus.WAITING_FOR_PAYMENT)
    assert not order.transition(VideoOrderStatus.REFUNDED).can_download(123)
