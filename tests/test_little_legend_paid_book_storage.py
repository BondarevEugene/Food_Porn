"""Paid-book asset keys and PDF envelopes are owner-scoped."""
import pytest

from app.little_legend.paid_book_storage import PaidBookStore, pdf_key


def test_pdf_key_is_stable_and_owner_scoped():
    assert pdf_key(quote_id=7, owner_id=10) == pdf_key(quote_id=7, owner_id=10)
    assert pdf_key(quote_id=7, owner_id=10) != pdf_key(quote_id=7, owner_id=11)
    assert pdf_key(quote_id=7, owner_id=10).endswith(".pdf")


@pytest.mark.parametrize("quote_id,owner_id", [(0, 1), (1, 0), (-1, 2)])
def test_invalid_book_key_rejected(quote_id, owner_id):
    with pytest.raises(ValueError):
        pdf_key(quote_id=quote_id, owner_id=owner_id)


def test_pdf_envelope_validation():
    PaidBookStore.validate(b"%PDF-1.7\nexample")
    with pytest.raises(ValueError):
        PaidBookStore.validate(b"not a PDF")
    with pytest.raises(ValueError):
        PaidBookStore.validate(b"%PDF-1.7" + b"x" * (32 * 1024 * 1024))
