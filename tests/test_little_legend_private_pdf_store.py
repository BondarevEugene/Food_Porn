"""Private PDF persistence, recovery and tampering regression tests."""
import hashlib
from unittest.mock import Mock

import pytest

from app.little_legend.book_delivery import BookDelivery
from app.little_legend.book_release import BookRelease
from app.little_legend.private_pdf_store import (
    pdf_object_key,
    persist_release_pdf,
    restore_release_pdf,
    validate_pdf,
)
from app.little_legend.release_package import ReleasePackage


def make_package() -> ReleasePackage:
    pdf = b"%PDF-" + b"hello" * 30
    digest = hashlib.sha256(pdf).hexdigest()
    return ReleasePackage(
        release=BookRelease(
            owner_id=1, story_id=2, revision_fingerprint="a" * 64,
            pdf_sha256=digest, scene_count=1,
        ),
        delivery=BookDelivery(owner_id=1, story_id=2, pdf_sha256=digest),
        pdf=pdf,
    )


def test_persist_and_restore_private_pdf() -> None:
    package = make_package()
    store = Mock()
    key = persist_release_pdf(store=store, package=package, owner_id=1, story_id=2)
    assert key.startswith("little-legend/releases/")
    store.put.assert_called_once_with(
        key=key, data=package.pdf, content_type="application/pdf",
    )
    store.get.return_value = package.pdf
    restored = restore_release_pdf(
        store=store, release=package.release, delivery=package.delivery,
        owner_id=1, story_id=2,
    )
    assert restored.pdf == package.pdf
    store.get.assert_called_once_with(key=key)


def test_foreign_owner_never_reads_or_writes() -> None:
    package = make_package()
    store = Mock()
    with pytest.raises(PermissionError):
        persist_release_pdf(store=store, package=package, owner_id=9, story_id=2)
    with pytest.raises(PermissionError):
        restore_release_pdf(
            store=store, release=package.release, delivery=package.delivery,
            owner_id=9, story_id=2,
        )
    store.put.assert_not_called()
    store.get.assert_not_called()


def test_tampered_stored_pdf_is_rejected() -> None:
    package = make_package()
    store = Mock()
    store.get.return_value = package.pdf + b"tampered"
    with pytest.raises(PermissionError, match="digest"):
        restore_release_pdf(
            store=store, release=package.release, delivery=package.delivery,
            owner_id=1, story_id=2,
        )


def test_invalid_key_and_pdf_are_rejected() -> None:
    with pytest.raises(ValueError):
        pdf_object_key(owner_id=1, story_id=2, pdf_sha256="../wrong")
    with pytest.raises(ValueError):
        validate_pdf(b"not a PDF", expected_sha256="a" * 64)


def test_pdf_keys_are_owner_scoped() -> None:
    digest = "f" * 64
    assert pdf_object_key(owner_id=1, story_id=2, pdf_sha256=digest) != (
        pdf_object_key(owner_id=2, story_id=2, pdf_sha256=digest)
    )
