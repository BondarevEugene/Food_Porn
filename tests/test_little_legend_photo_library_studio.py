"""Regression contracts for private photo library in the studio."""

from app.little_legend.router import STUDIO_HTML, router


def test_photo_library_is_an_authenticated_get_route() -> None:
    route = next(
        route for route in router.routes
        if getattr(route, "path", "") == "/little-legend/api/stories/{story_id}/photos"
        and "GET" in route.methods
    )
    assert any(dep.call.__name__ == "_owner" for dep in route.dependant.dependencies)


def test_photo_library_visible_after_upload_and_reopening() -> None:
    assert 'id="photoLibraryStatus"' in STUDIO_HTML
    assert "async function refreshPhotoLibrary()" in STUDIO_HTML
    assert "await refreshPhotoConsent();await refreshPhotoLibrary()" in STUDIO_HTML
    assert "await refreshPhotoLibrary();" in STUDIO_HTML
    assert "Загруженных фотографий пока нет." in STUDIO_HTML
