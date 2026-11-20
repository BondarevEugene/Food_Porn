"""Art Director readiness UI is read-only and owner-scoped."""
from app.little_legend.router import STUDIO_HTML, read_art_readiness


def test_art_readiness_screen_has_safe_read_only_flow():
    assert "openArtReadiness()" in STUDIO_HTML
    assert "/art-readiness" in STUDIO_HTML
    assert "artReadinessScenes" in STUDIO_HTML
    assert "artReadinessBlockers" in STUDIO_HTML
    assert "report.scenes_ready" in STUDIO_HTML


def test_art_readiness_endpoint_is_owner_scoped():
    import inspect

    signature = inspect.signature(read_art_readiness)
    assert "story_id" in signature.parameters
    assert "owner" in signature.parameters
    assert "inspect_book_art" in inspect.getsource(read_art_readiness)
    assert "_owned_draft(story_id, owner)" in inspect.getsource(
        read_art_readiness,
    )
