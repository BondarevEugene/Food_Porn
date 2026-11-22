"""Regression contracts for the Little Legend in-studio photo consent flow."""

from app.little_legend.router import STUDIO_HTML, router


def test_photo_consent_routes_are_owner_authenticated() -> None:
    paths = [
        route for route in router.routes
        if getattr(route, "path", "").endswith("/photo-consent")
    ]
    assert {method for route in paths for method in route.methods} >= {
        "GET", "POST", "DELETE",
    }
    for route in paths:
        assert any(
            dependency.call.__name__ == "_owner"
            for dependency in route.dependant.dependencies
        )


def test_consent_notice_and_explicit_checkbox_in_studio() -> None:
    assert 'id="photoConsentNotice"' in STUDIO_HTML
    assert 'id="photoParentConsent" type="checkbox"' in STUDIO_HTML
    assert "async function confirmPhotoConsent()" in STUDIO_HTML
    assert "async function revokePhotoConsent()" in STUDIO_HTML
    assert "accepted_notice:currentPhotoNotice" in STUDIO_HTML
    assert "parent_authorized:true" in STUDIO_HTML


def test_private_upload_requires_separate_consent() -> None:
    assert "async function refreshPhotoConsent()" in STUDIO_HTML
    assert "await refreshPhotoConsent()" in STUDIO_HTML
    assert "Сначала подтвердите отдельное согласие" in STUDIO_HTML
    assert "Фото поставлены в очередь удаления" in STUDIO_HTML
