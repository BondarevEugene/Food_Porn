"""Premium photo-aware queue must be owner-scoped and consent-gated."""

from app.little_legend.router import router


def test_premium_queue_requires_authenticated_owner() -> None:
    route = next(
        route for route in router.routes
        if getattr(route, "path", "").endswith("/illustrations/premium-queue")
    )
    assert "POST" in route.methods
    assert any(dep.call.__name__ == "_owner" for dep in route.dependant.dependencies)


def test_premium_queue_is_distinct_from_standard_queue() -> None:
    paths = {getattr(route, "path", "") for route in router.routes}
    assert "/little-legend/api/stories/{story_id}/illustrations/queue" in paths
    assert "/little-legend/api/stories/{story_id}/illustrations/premium-queue" in paths
