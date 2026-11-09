"""Telegram Stars invoice payloads identify video stories independently."""

from app.services.stars import OrderRef, parse_payload


def test_video_story_stars_payload_roundtrip():
    ref = OrderRef("video_story", 12, 456, 75)
    assert parse_payload(ref.payload) == ref
    assert parse_payload(ref.payload).kind != "wallpaper"


def test_video_story_stars_rejects_tampering():
    assert parse_payload("fp:video_story:12:456:0") is None
    assert parse_payload("fp:video_story:12:456:75:extra") is None
    assert parse_payload("fp:video_story:12:456:075") is None
