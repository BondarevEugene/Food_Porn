"""Print package caching must be safe across retries and source updates."""
from zipfile import ZipFile

from PIL import Image

from app.services.print_bundle import create_print_bundle


def _inputs(tmp_path):
    mobile = tmp_path / "mobile.png"
    desktop = tmp_path / "desktop.png"
    Image.new("RGB", (540, 960), "red").save(mobile)
    Image.new("RGB", (960, 540), "blue").save(desktop)
    return mobile, desktop


def _bundle(mobile, desktop):
    return create_print_bundle(37, mobile, desktop, width_mm=60, height_mm=80, dpi=72)


def test_corrupt_cached_zip_is_rebuilt(tmp_path):
    mobile, desktop = _inputs(tmp_path)
    archive = _bundle(mobile, desktop)
    archive.write_bytes(b"broken ZIP from interrupted write")
    rebuilt = _bundle(mobile, desktop)
    assert rebuilt == archive
    with ZipFile(rebuilt) as package:
        assert package.testzip() is None
        assert package.read("mobile_original.png") == mobile.read_bytes()


def test_changed_photo_invalidates_cached_zip(tmp_path):
    mobile, desktop = _inputs(tmp_path)
    archive = _bundle(mobile, desktop)
    with ZipFile(archive) as package:
        old_photo = package.read("mobile_original.png")
    Image.new("RGB", (540, 960), "green").save(mobile)
    # Explicitly advance the source mtime for filesystems with coarse clocks.
    import os
    old_ns = archive.stat().st_mtime_ns
    os.utime(mobile, ns=(old_ns + 2_000_000_000, old_ns + 2_000_000_000))
    rebuilt = _bundle(mobile, desktop)
    with ZipFile(rebuilt) as package:
        assert package.read("mobile_original.png") == mobile.read_bytes()
        assert package.read("mobile_original.png") != old_photo
