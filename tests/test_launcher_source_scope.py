"""Archives in the project root must not block the running source."""

import launcher


def test_launcher_checks_only_real_project_sources(tmp_path, monkeypatch):
    (tmp_path / "launcher.py").write_text("x = 1\n", encoding="utf-8")
    source = tmp_path / "app" / "main.py"
    source.parent.mkdir()
    source.write_text("value = 7\n", encoding="utf-8")
    broken = tmp_path / "Food_Porn_gift_backup_123" / "app" / "services" / "old.py"
    broken.parent.mkdir(parents=True)
    broken.write_text("    unexpected indent\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "ROOT", tmp_path)

    assert [p.relative_to(tmp_path).as_posix() for p in launcher.project_python_files()] == [
        "app/main.py", "launcher.py",
    ]
    assert launcher.ruff_source_paths() == ["app", "launcher.py"]
    assert launcher.check_python_syntax().status == launcher.Status.PASS
