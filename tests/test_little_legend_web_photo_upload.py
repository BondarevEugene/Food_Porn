"""Contract regression tests for the private web photo upload endpoint."""
import ast
from pathlib import Path


SOURCE = Path("app/little_legend/router.py").read_text(encoding="utf-8")


def test_upload_is_authenticated_and_owner_scoped() -> None:
    tree = ast.parse(SOURCE)
    endpoint = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "upload_story_photo"
    )
    text = ast.get_source_segment(SOURCE, endpoint)
    assert "Depends(_owner)" in text
    assert "await _owned_draft(story_id, owner)" in text
    assert "upload_consented_child_photo(" in text
    assert "NeonPremiumPhotoConsentRepository()" in text


def test_upload_limits_size_and_type_before_storage() -> None:
    assert 'raise HTTPException(413, "Photo exceeds 12 MiB")' in SOURCE
    assert 'raise HTTPException(415, "JPEG, PNG or WebP required")' in SOURCE
    assert "async for chunk in request.stream()" in SOURCE
    assert "S3PrivatePhotoStore(store_settings_from_environment())" in SOURCE


def test_studio_exposes_file_input_and_403_consent_message() -> None:
    assert 'id="photoUploadInput" type="file"' in SOURCE
    assert "async function uploadPhoto()" in SOURCE
    assert "if(r.status===403)" in SOURCE
    assert "if(r.status===401){authRejected();" in SOURCE
