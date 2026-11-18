"""A paid gift quote must describe the exact source photos used for pricing."""
from decimal import Decimal
from hashlib import sha256

from app.services.gift_purchases import quote_key


def _key(photo_digests):
    return quote_key(
        42, choice="both", goals=["a", "b", "c", "d", "e"],
        photos=["/tmp/gift/photo.png"], style="light",
        collage_amount=Decimal("100.00"), video_amount=Decimal("50.00"),
        photo_digests=photo_digests,
    )


def test_photo_replacement_at_same_path_changes_quote_identity():
    original = sha256(b"first photo").hexdigest()
    replacement = sha256(b"second photo").hexdigest()
    assert _key([original]) != _key([replacement])


def test_same_photo_bytes_keep_quote_idempotent():
    digest = sha256(b"same image").hexdigest()
    assert _key([digest]) == _key([digest])


def test_photo_order_affects_quote_identity():
    first = sha256(b"one").hexdigest()
    second = sha256(b"two").hexdigest()
    assert _key([first, second]) != _key([second, first])
