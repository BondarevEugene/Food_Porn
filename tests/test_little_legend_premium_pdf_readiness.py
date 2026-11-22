"""Premium batches must never be advertised as standard downloadable PDFs."""

from app.little_legend.router import STUDIO_HTML, router


def test_production_overview_exposes_pdf_specific_readiness() -> None:
    route = next(
        route for route in router.routes
        if getattr(route, "path", "").endswith("/production-overview")
    )
    assert "GET" in route.methods
    assert any(dep.call.__name__ == "_owner" for dep in route.dependant.dependencies)


def test_download_ui_uses_pdf_readiness_not_generic_job_completion() -> None:
    assert "if(!result.pdf_ready)" in STUDIO_HTML
    assert "result.pdf_blocker" in STUDIO_HTML
    assert "result.all_illustrations_complete||!result.has_manuscript" not in STUDIO_HTML
