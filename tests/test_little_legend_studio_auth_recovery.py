"""Regression checks for the embedded Little Legend Telegram studio shell.

These checks deliberately avoid a live Telegram session or database.
"""
from __future__ import annotations

import ast
from pathlib import Path


def _studio_html() -> str:
    source = Path("app/little_legend/router.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    return next(
        ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "STUDIO_HTML" for target in node.targets)
    )


def test_studio_never_sends_missing_telegram_launch_data() -> None:
    html = _studio_html()
    assert "if(!auth){authRejected();" in html
    assert "if(r.status===401){authRejected();" in html
    assert "$('workspace').classList.add('hidden')" in html
    assert "cache:'no-store'" in html


def test_studio_does_not_duplicate_parallel_story_creates() -> None:
    html = _studio_html()
    assert "if(saving)return;" in html
    assert "saving=true;" in html
    assert "finally{saving=false}" in html
    assert "storyId=storyId||result.id" in html


def test_studio_preserves_success_when_list_refresh_fails() -> None:
    html = _studio_html()
    assert "Черновик сохранён, но список книг не обновился" in html
    assert "Ошибка сохранения:" in html
    assert "Закройте студию и откройте её заново" in html
