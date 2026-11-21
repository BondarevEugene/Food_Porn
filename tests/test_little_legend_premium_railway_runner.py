"""Premium Railway service must fail closed before acquiring any paid job."""
import pytest

from app.little_legend.premium_railway_runner import configured_premium_worker


def test_premium_worker_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LL_PREMIUM_WORKER_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="disabled"):
        configured_premium_worker()


def test_premium_worker_requires_final_photo_disclosure(monkeypatch):
    monkeypatch.setenv("LL_PREMIUM_WORKER_ENABLED", "true")
    monkeypatch.delenv("LL_PREMIUM_PHOTO_AI_CONSENT_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="disclosure"):
        configured_premium_worker()


def test_premium_worker_requires_pricing_approval(monkeypatch):
    monkeypatch.setenv("LL_PREMIUM_WORKER_ENABLED", "true")
    monkeypatch.setenv("LL_PREMIUM_PHOTO_AI_CONSENT_ENABLED", "true")
    monkeypatch.setenv("LL_PREMIUM_PHOTO_AI_PROVIDER", "Provider")
    monkeypatch.setenv("LL_PREMIUM_PHOTO_AI_LEGAL_ENTITY", "Provider Ltd")
    monkeypatch.setenv("LL_PREMIUM_PHOTO_AI_COUNTRIES", "EU")
    monkeypatch.setenv("LL_PREMIUM_PHOTO_AI_RETENTION", "7 days")
    monkeypatch.setenv("LL_PREMIUM_PHOTO_AI_PRIVACY_URL", "https://example.com/privacy")
    monkeypatch.delenv("LL_PREMIUM_PRICING_APPROVED", raising=False)
    with pytest.raises(RuntimeError, match="pricing"):
        configured_premium_worker()
