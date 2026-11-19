"""Release package guards: no provider calls, real PDF hash and owner binding."""
import hashlib
from unittest.mock import Mock, patch

import pytest

from app.little_legend.book_delivery import BookDelivery
from app.little_legend.book_release import BookRelease
from app.little_legend.release_package import ReleasePackage, build_release_package


def make_package() -> ReleasePackage:
    pdf = b"%PDF-" + b"example" * 25
    digest = hashlib.sha256(pdf).hexdigest()
    return ReleasePackage(
        release=BookRelease(
            owner_id=10, story_id=20,
            revision_fingerprint="a" * 64, pdf_sha256=digest,
            scene_count=1,
        ),
        delivery=BookDelivery(
            owner_id=10, story_id=20, pdf_sha256=digest,
        ),
        pdf=pdf,
    )


def test_valid_release_package_verifies_pdf() -> None:
    package = make_package()
    assert package.verified_pdf(owner_id=10, story_id=20) == package.pdf


def test_wrong_owner_or_story_is_denied() -> None:
    package = make_package()
    with pytest.raises(PermissionError):
        package.verified_pdf(owner_id=11, story_id=20)
    with pytest.raises(PermissionError):
        package.verified_pdf(owner_id=10, story_id=21)


def test_tampered_pdf_is_denied() -> None:
    package = make_package()
    changed = package.model_copy(update={"pdf": package.pdf + b"modified"})
    with pytest.raises(PermissionError, match="differs"):
        changed.verified_pdf(owner_id=10, story_id=20)


def test_wrong_delivery_hash_is_denied() -> None:
    package = make_package()
    delivery = package.delivery.model_copy(update={"pdf_sha256": "b" * 64})
    changed = package.model_copy(update={"delivery": delivery})
    with pytest.raises(PermissionError, match="delivery"):
        changed.verified_pdf(owner_id=10, story_id=20)


def test_missing_editorial_approval_never_reads_storage() -> None:
    store = Mock()
    with pytest.raises(PermissionError, match="Editorial approval"):
        build_release_package(
            owner_id=10, story_id=20, title="Story", dedication="For you",
            graph=Mock(), manuscript=Mock(), jobs=[], store=store,
            editorial_approved=False,
        )
    store.get.assert_not_called()


def test_wrong_owner_art_is_denied_before_storage_reads() -> None:
    store = Mock()
    job = Mock(owner_id=99, story_id=20)
    with pytest.raises(PermissionError, match="another owner"):
        build_release_package(
            owner_id=10, story_id=20, title="Story", dedication="For you",
            graph=Mock(), manuscript=Mock(), jobs=[job], store=store,
            editorial_approved=True,
        )
    store.get.assert_not_called()


def test_successful_package_seals_assembly_once() -> None:
    expected = make_package()
    with (
        patch("app.little_legend.release_package.assemble_private_book", return_value=expected.pdf) as assemble,
        patch("app.little_legend.release_package.seal_book_release", return_value=expected.release) as seal,
        patch("app.little_legend.release_package.verify_book_release") as verify,
    ):
        result = build_release_package(
            owner_id=10, story_id=20, title="Story", dedication="For you",
            graph=Mock(), manuscript=Mock(), jobs=[], store=Mock(),
            editorial_approved=True,
        )
    assert result.verified_pdf(owner_id=10, story_id=20) == expected.pdf
    assemble.assert_called_once()
    seal.assert_called_once()
    verify.assert_called_once()
