"""Regression checks for safe MP4 publication and mobile style choices."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_video_is_published_only_after_ffmpeg_succeeds():
    source = (ROOT / "app/services/wallpaper_studio.py").read_text(encoding="utf-8")
    method = source.split("    def _render_video_sync(", 1)[1].split("    @staticmethod", 1)[0]
    assert "subprocess.run(command, check=True, timeout=300)" in method
    assert "pending.stat().st_size < 1024" in method
    assert "staged.replace(destination)" in method
    assert method.index("subprocess.run(command") < method.index("staged.replace(destination)")


def test_gift_style_buttons_have_individual_rows():
    source = (ROOT / "app/bot/handlers/wallpaper.py").read_text(encoding="utf-8")
    method = source.split("def gift_keyboard(", 1)[1].split("def gift_review_text(", 1)[0]
    assert ")] for key, uk, ru, en in styles" in method
    assert 'callback_data="gift_back_to_product"' in method
