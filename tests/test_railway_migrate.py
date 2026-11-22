"""Railway migration entry point must fail closed and never leak secrets."""
from types import SimpleNamespace

from app.ops import railway_migrate


def test_migration_runs_current_upgrade_current(monkeypatch):
    calls = []
    monkeypatch.setattr(
        railway_migrate, "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql+asyncpg://test:secret@localhost/neondb",
        ),
    )
    monkeypatch.setattr(
        railway_migrate.command, "current",
        lambda *_args, **_kwargs: calls.append("current"),
    )
    monkeypatch.setattr(
        railway_migrate.command, "upgrade",
        lambda *_args: calls.append("upgrade"),
    )
    assert railway_migrate.main() == 0
    assert calls == ["current", "upgrade", "current"]


def test_migration_failure_blocks_deployment(monkeypatch):
    monkeypatch.setattr(
        railway_migrate, "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql+asyncpg://test:secret@localhost/neondb",
        ),
    )

    def fail(*_args, **_kwargs):
        raise RuntimeError("migration unavailable")

    monkeypatch.setattr(railway_migrate.command, "current", fail)
    assert railway_migrate.main() == 1
