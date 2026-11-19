"""PDF delivery idempotency tests without network or database calls."""
import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from app.little_legend.book_delivery import BookDelivery, DeliveryStatus
from app.little_legend.book_release import BookRelease
from app.little_legend.production_effect_ledger import EffectKind, EffectStatus
from app.little_legend.release_package import ReleasePackage
from app.little_legend.telegram_pdf_dispatch import (
    dispatch_release_pdf,
    pdf_delivery_effect_key,
)


def package() -> ReleasePackage:
    pdf = b"%PDF-" + b"test" * 50
    digest = hashlib.sha256(pdf).hexdigest()
    return ReleasePackage(
        release=BookRelease(
            owner_id=11, story_id=22, revision_fingerprint="a" * 64,
            pdf_sha256=digest, scene_count=1,
        ),
        delivery=BookDelivery(owner_id=11, story_id=22, pdf_sha256=digest),
        pdf=pdf,
    )


@pytest.mark.asyncio
async def test_success_fences_before_sending_and_confirms() -> None:
    calls = []
    async def reserve(**kwargs):
        calls.append("reserve")
        return type("Effect", (), {"status": EffectStatus.RESERVED})(), True

    async def transition(**kwargs):
        calls.append(kwargs["next_status"].value)

    async def send_pdf(**kwargs):
        calls.append("send")
        assert kwargs["chat_id"] == 11
        assert kwargs["pdf"].startswith(b"%PDF-")
        return 456

    with (
        patch("app.little_legend.telegram_pdf_dispatch.reserve_effect", side_effect=reserve),
        patch("app.little_legend.telegram_pdf_dispatch.transition_effect", side_effect=transition),
    ):
        delivery = await dispatch_release_pdf(
            package=package(), owner_id=11, story_id=22,
            sender=type("Sender", (), {"send_pdf": AsyncMock(side_effect=send_pdf)})(),
        )
    assert calls == ["reserve", "dispatched", "send", "confirmed"]
    assert delivery.status == DeliveryStatus.SENT
    assert delivery.telegram_message_id == 456


@pytest.mark.asyncio
async def test_duplicate_never_sends() -> None:
    sender = AsyncMock()
    with patch(
        "app.little_legend.telegram_pdf_dispatch.reserve_effect",
        return_value=(type("Effect", (), {"status": EffectStatus.DISPATCHED})(), False),
    ):
        with pytest.raises(PermissionError, match="already"):
            await dispatch_release_pdf(
                package=package(), owner_id=11, story_id=22, sender=sender,
            )
    sender.send_pdf.assert_not_awaited()


@pytest.mark.asyncio
async def test_timeout_is_uncertain_and_never_retries() -> None:
    sender = AsyncMock()
    sender.send_pdf.side_effect = TimeoutError("unknown outcome")
    with (
        patch(
            "app.little_legend.telegram_pdf_dispatch.reserve_effect",
            return_value=(type("Effect", (), {"status": EffectStatus.RESERVED})(), True),
        ),
        patch(
            "app.little_legend.telegram_pdf_dispatch.transition_effect",
            new_callable=AsyncMock,
        ) as transition,
    ):
        result = await dispatch_release_pdf(
            package=package(), owner_id=11, story_id=22, sender=sender,
        )
    assert result.status == DeliveryStatus.UNCERTAIN
    assert sender.send_pdf.await_count == 1
    assert transition.await_args.kwargs["next_status"] == EffectStatus.UNCERTAIN


@pytest.mark.asyncio
async def test_wrong_owner_never_reserves_or_sends() -> None:
    sender = AsyncMock()
    with patch(
        "app.little_legend.telegram_pdf_dispatch.reserve_effect",
        new_callable=AsyncMock,
    ) as reserve:
        with pytest.raises(PermissionError):
            await dispatch_release_pdf(
                package=package(), owner_id=12, story_id=22, sender=sender,
            )
    reserve.assert_not_awaited()
    sender.send_pdf.assert_not_awaited()


def test_effect_key_is_deterministic_and_owner_scoped() -> None:
    digest = "b" * 64
    first = pdf_delivery_effect_key(owner_id=11, story_id=22, pdf_sha256=digest)
    assert first == pdf_delivery_effect_key(owner_id=11, story_id=22, pdf_sha256=digest)
    assert first != pdf_delivery_effect_key(owner_id=12, story_id=22, pdf_sha256=digest)
    assert first.startswith("llpdf:")
    assert len(first) <= 120
    assert EffectKind.TELEGRAM_PDF.value == "telegram_pdf"
