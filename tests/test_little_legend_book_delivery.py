"""No duplicate sends when a PDF delivery is uncertain or acknowledged."""
import pytest

from app.little_legend.book_delivery import (
    BookDelivery,
    DeliveryStatus,
    begin_delivery,
    confirm_delivery,
    mark_uncertain,
)


def _ready():
    return BookDelivery(owner_id=3, story_id=2, pdf_sha256="a" * 64)


def test_successful_delivery_is_acknowledged_once():
    reserved = begin_delivery(_ready(), attempt_id="attempt-1")
    assert reserved.status == DeliveryStatus.SENDING
    sent = confirm_delivery(reserved, attempt_id="attempt-1", message_id=42)
    assert sent.status == DeliveryStatus.SENT
    assert sent.telegram_message_id == 42
    assert sent.sent_at is not None
    with pytest.raises(PermissionError):
        begin_delivery(sent, attempt_id="attempt-2")


def test_timeout_requires_reconciliation_not_automatic_resend():
    reserved = begin_delivery(_ready(), attempt_id="attempt-1")
    uncertain = mark_uncertain(reserved, attempt_id="attempt-1")
    assert uncertain.status == DeliveryStatus.UNCERTAIN
    with pytest.raises(PermissionError):
        begin_delivery(uncertain, attempt_id="attempt-2")
    with pytest.raises(PermissionError):
        confirm_delivery(uncertain, attempt_id="attempt-1", message_id=42)


def test_wrong_attempt_cannot_confirm_or_mark_uncertain():
    reserved = begin_delivery(_ready(), attempt_id="attempt-1")
    with pytest.raises(PermissionError):
        confirm_delivery(reserved, attempt_id="wrong", message_id=42)
    with pytest.raises(PermissionError):
        mark_uncertain(reserved, attempt_id="wrong")


def test_invalid_attempt_and_message_id_are_rejected():
    with pytest.raises(ValueError):
        begin_delivery(_ready(), attempt_id=" ")
    reserved = begin_delivery(_ready(), attempt_id="attempt-1")
    with pytest.raises(PermissionError):
        confirm_delivery(reserved, attempt_id="attempt-1", message_id=0)


def test_invalid_owner_or_pdf_fingerprint_is_rejected():
    with pytest.raises(ValueError):
        BookDelivery(owner_id=0, story_id=2, pdf_sha256="a" * 64)
    with pytest.raises(ValueError):
        BookDelivery(owner_id=3, story_id=2, pdf_sha256="invalid")
