"""Regression guards for video purchase UI and existing collage controls."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/miniapp/static/app.js").read_text(encoding="utf-8")
API = (ROOT / "app/miniapp/api.py").read_text(encoding="utf-8")


def test_existing_collage_actions_remain_available():
    for action in (
        "studio-scene", "studio-lock", "studio-generate",
        "studio-select", "studio-exports", "studio-download",
    ):
        assert f"if (action === '{action}')" in JS


def test_video_is_separately_ordered_and_paid():
    assert "video-story/orders', {method:'POST'}" in JS
    for action in ("video-checkout", "video-verify", "video-download"):
        assert f"if (action === '{action}')" in JS
    assert "if (!state.videoStory?.paid)" in JS


def test_video_order_restores_on_studio_open():
    assert "video-story/orders/latest" in JS
    assert "latest.order || null" in JS
    assert "Video order lookup must never prevent access" in JS


def test_video_has_owner_only_download_and_no_legacy_collage_export():
    assert '@router.get("/api/video-stories/{video_order_id}/file")' in API
    assert 'video.telegram_user_id != user["id"]' in API
    assert "Use the video story order download endpoint" in API


def test_stars_only_pricing_does_not_require_wayforpay():
    assert 'settings.wayforpay_video_story_price_uah or Decimal("0.00")' in API
    assert 'if provider != "stars":' in API


def test_video_payment_options_are_server_filtered():
    assert '@router.get("/api/video-stories/payment-options")' in API
    assert 'WayForPayService(settings).ready' in API
    assert 'PaymentService(settings).portmone_ready' in API
    assert 'settings.video_story_price_stars > 0' in API
    assert "state.videoProviders = methods.providers || []" in JS
    assert "(state.videoProviders || []).map(item =>" in JS


def test_stars_checkout_refreshes_order_from_server():
    assert "tg.openInvoice(url, async status =>" in JS
    assert "video-story/orders/latest" in JS
