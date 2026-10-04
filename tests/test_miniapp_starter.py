"""Temporary tunnel failures must not leave the bot pointing at a dead URL."""

import pytest

import start_food_porn_miniapp as starter


def test_starter_recreates_the_tunnel_after_a_disconnect(monkeypatch, tmp_path):
    (tmp_path / "run.py").touch()
    (tmp_path / "app" / "miniapp").mkdir(parents=True)
    (tmp_path / "app" / "miniapp" / "api.py").touch()
    monkeypatch.setattr(starter, "ROOT", tmp_path)
    calls = []
    delays = []

    def run():
        calls.append("run")
        if len(calls) == 1:
            raise starter.TunnelLost("Error 1033")
        return 0

    monkeypatch.setattr(starter, "run_session", run)
    monkeypatch.setattr(starter.time, "sleep", delays.append)

    assert starter.main() == 0
    assert len(calls) == 2
    assert delays == [2]


def test_starter_stops_after_repeated_tunnel_failures(monkeypatch, tmp_path):
    (tmp_path / "run.py").touch()
    (tmp_path / "app" / "miniapp").mkdir(parents=True)
    (tmp_path / "app" / "miniapp" / "api.py").touch()
    monkeypatch.setattr(starter, "ROOT", tmp_path)
    calls = []

    def fail():
        calls.append(1)
        raise starter.TunnelLost("offline")

    monkeypatch.setattr(starter, "run_session", fail)
    monkeypatch.setattr(starter.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="5 попыток"):
        starter.main()
    assert len(calls) == 5
