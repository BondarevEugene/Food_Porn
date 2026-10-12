"""
==========================================================
FOOD_PORN

Module: Railway Bootstrap Tests
Layer: Quality Assurance

Responsibilities:
    - Verify one canonical FastAPI application
    - Verify Mini App and payment routes survive admin mounting
    - Verify the Railway healthcheck endpoint is registered
==========================================================
"""

from types import SimpleNamespace

import pytest

import main

app = main.app


def test_canonical_application_contains_public_routes() -> None:
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    for route in app.routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            paths.update(child.path for child in included.routes if hasattr(child, "path"))

    assert "/health" in paths
    assert "/miniapp" in paths
    assert "/miniapp/api/home" in paths
    assert "/portmone/callback" in paths
    assert "/admin" in paths


def test_railway_port_has_priority(monkeypatch) -> None:
    monkeypatch.setenv("PORT", "9123")
    assert main.resolve_web_port(SimpleNamespace(miniapp_port=8080)) == 9123


def test_local_port_is_used_without_railway(monkeypatch) -> None:
    monkeypatch.delenv("PORT", raising=False)
    assert main.resolve_web_port(SimpleNamespace(miniapp_port=8080)) == 8080


@pytest.mark.parametrize("value", ["not-a-number", "0", "70000"])
def test_invalid_railway_port_is_rejected(monkeypatch, value) -> None:
    monkeypatch.setenv("PORT", value)
    with pytest.raises(RuntimeError, match="port"):
        main.resolve_web_port(SimpleNamespace(miniapp_port=8080))
