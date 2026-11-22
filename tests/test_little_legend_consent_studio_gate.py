"""Consent-first photo constructor with a private, gated upload."""
from app.little_legend.consent import ConsentDecision, ConsentRecord, record_decision
from app.little_legend.router import STUDIO_HTML


def test_consent_is_required_for_story_photo_constructor():
    assert "async function openPhotoConstructor()" in STUDIO_HTML
    assert "if(!x.status.terms_accepted)" in STUDIO_HTML
    assert "await openPhotoConstructor()" in STUDIO_HTML
    assert "if(!x.status.terms_accepted)throw Error" in STUDIO_HTML


def test_checkbox_requires_explicit_parent_and_terms():
    assert "consentContinue" in STUDIO_HTML
    assert "consentChecksChanged" in STUDIO_HTML
    assert "consentTermsCheck').checked=false" in STUDIO_HTML
    assert "consentParentCheck').checked=false" in STUDIO_HTML
    assert "consent_to_child_photos:false" in STUDIO_HTML


def test_photo_constructor_accepts_private_files_after_consent():
    section = STUDIO_HTML.split('<section id="photoConstructor"', 1)[1].split(
        '<section id="identity"', 1,
    )[0]
    assert 'id="photoUploadInput" type="file"' in section
    assert 'accept="image/jpeg,image/png,image/webp"' in section
    assert "Загрузить фото приватно" in section
    assert "Продолжить без фото" in section
    assert "if(r.status===403)" in STUDIO_HTML
    assert "Сначала подтвердите отдельное согласие" in STUDIO_HTML


def test_photo_consent_remains_fail_closed():
    previous = ConsentRecord()
    try:
        record_decision(
            previous,
            ConsentDecision(
                accept_terms=True,
                declare_parental_authority=True,
                consent_to_child_photos=True,
            ),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Photo consent must remain unavailable")
