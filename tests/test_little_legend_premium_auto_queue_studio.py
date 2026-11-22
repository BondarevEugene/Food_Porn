"""One-click premium queue remains authenticated and explicit."""

from app.little_legend.router import STUDIO_HTML, router


def test_premium_auto_queue_is_owner_scoped() -> None:
    route = next(
        route for route in router.routes
        if getattr(route, "path", "").endswith("/illustrations/premium-auto-queue")
    )
    assert "POST" in route.methods
    assert any(dep.call.__name__ == "_owner" for dep in route.dependant.dependencies)


def test_studio_exposes_one_click_premium_production() -> None:
    assert 'id="premiumGenre"' in STUDIO_HTML
    assert "async function startPremiumProduction()" in STUDIO_HTML
    assert "/illustrations/premium-auto-queue" in STUDIO_HTML
    assert "Запустить персонализированные иллюстрации" in STUDIO_HTML
