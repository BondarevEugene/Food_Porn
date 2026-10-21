"""Scene Studio keeps approved pixels, versions and delivery formats deterministic."""

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from app.services import wallpaper_studio as studio


def _image(path: Path, size: tuple[int, int], color: str) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def test_scene_geometry_covers_each_supported_layout() -> None:
    for count in range(5, 10):
        for ratio in ("9:16", "16:9"):
            for index in range(count):
                x0, y0, x1, y1 = studio.scene_bounds(count, index, ratio)
                assert 0 <= x0 < x1 <= 1
                assert 0 <= y0 < y1 <= 1


def test_source_archive_survives_upload_cleanup(tmp_path: Path) -> None:
    source = _image(tmp_path / "upload.png", (1800, 1200), "#a06050")
    archived = studio.archive_source_photos([source], tmp_path / "order")
    source.unlink()
    saved = Path(archived[0])
    assert saved.is_file()
    with Image.open(saved) as image:
        assert image.mode == "RGB"
        assert max(image.size) <= 1600


def test_scene_blend_preserves_pixels_outside_selected_region() -> None:
    canvas = Image.new("RGB", (600, 1000), "#102030")
    variant = Image.new("RGB", (500, 500), "#e8a050")
    bounds = studio.scene_bounds(5, 2, "9:16")
    result = studio.WallpaperSceneEditor._blend_scene(canvas, variant, bounds)
    assert result.getpixel((599, 0)) == canvas.getpixel((599, 0))
    box = studio._pixel_box(canvas, bounds)
    center = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
    assert result.getpixel(center) != canvas.getpixel(center)


def test_static_formats_are_derived_without_ai_calls(tmp_path: Path, monkeypatch) -> None:
    mobile = _image(tmp_path / "mobile.png", (360, 640), "#533a55")
    desktop = _image(tmp_path / "desktop.png", (640, 360), "#355348")
    order = SimpleNamespace(mobile_path=str(mobile), desktop_path=str(desktop))
    monkeypatch.setattr(studio, "STATIC_FORMATS", {
        "phone": (180, 320), "desktop": (320, 180), "story": (180, 320),
        "instagram": (200, 200), "a3": (210, 297), "telegram": (320, 180),
    })
    exports = studio.WallpaperExportService(order).render_static()
    assert set(exports) == {"phone", "desktop", "story", "instagram", "a3", "telegram"}
    for kind, (path, width, height) in exports.items():
        assert path.is_file(), kind
        with Image.open(path) as image:
            assert image.size == (width, height)


def test_current_scene_preview_uses_raw_artwork(tmp_path: Path) -> None:
    raw = _image(tmp_path / "raw.png", (600, 1000), "#a17f61")
    labelled = _image(tmp_path / "labelled.png", (600, 1000), "#111111")
    order = SimpleNamespace(
        raw_mobile_path=str(raw), mobile_path=str(labelled), goals=[str(value) for value in range(5)]
    )
    destination = studio.current_scene_preview(order, 0, tmp_path / "preview.png")
    with Image.open(destination) as image:
        assert image.getpixel((image.width // 2, image.height // 2)) == (161, 127, 97)


def test_ambient_soundtrack_has_expected_duration(tmp_path: Path) -> None:
    path = tmp_path / "ambient.wav"
    studio.WallpaperExportService._ambient_track(path, 10)
    import wave
    with wave.open(str(path), "rb") as audio:
        assert audio.getnframes() == audio.getframerate() * 10
        assert audio.getnchannels() == 1
