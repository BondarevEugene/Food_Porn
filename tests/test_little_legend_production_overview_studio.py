"""Production overview regression contracts."""

from app.little_legend.router import STUDIO_HTML, router


def test_production_overview_owner_scoped() -> None:
    route = next(
        route for route in router.routes
        if getattr(route, "path", "").endswith("/production-overview")
    )
    assert "GET" in route.methods
    assert any(dep.call.__name__ == "_owner" for dep in route.dependant.dependencies)


def test_studio_exposes_production_status_and_private_pdf_download() -> None:
    assert 'id="productionOverviewStatus"' in STUDIO_HTML
    assert "async function refreshProductionOverview()" in STUDIO_HTML
    assert "async function downloadCompletedBook()" in STUDIO_HTML
    assert "if(!result.all_illustrations_complete||!result.has_manuscript)" in STUDIO_HTML
    assert "Authorization:'tma '+auth" in STUDIO_HTML
