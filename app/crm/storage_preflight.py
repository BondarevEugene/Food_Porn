"""Read-only deletion preflight for Mini CRM R2 objects.

No deletion capability is exposed here. Inventory and ownership must both be
complete; unknown objects remain protected.
"""
from __future__ import annotations

from typing import Any


def inspect_selection(
    inventory: dict[str, Any],
    *,
    bot_id: str,
    provider: str,
    keys: list[str],
) -> dict[str, Any]:
    if not keys or len(keys) > 100 or len(keys) != len(set(keys)):
        raise ValueError("Выберите от 1 до 100 разных файлов")
    matches = [
        p for p in inventory.get("providers", [])
        if p["bot_id"] == bot_id and p["provider"] == provider
    ]
    if len(matches) != 1:
        raise ValueError("Подключение не найдено или неоднозначно")
    connection = matches[0]
    if connection["status"] != "ok" or connection.get("truncated"):
        raise ValueError("Неполная инвентаризация: проверка невозможна")
    objects = {obj["key"]: obj for obj in connection["objects"]}
    if any(key not in objects for key in keys):
        raise ValueError("Выбранный файл отсутствует в актуальной инвентаризации")
    linked = {}
    for book in inventory.get("books", []):
        for file in book.get("files", []):
            if file.get("provider") == provider:
                linked[file["key"]] = {
                    "story_id": book.get("story_id"),
                    "kind": file.get("kind", "unknown"),
                    "status": file.get("status", "unknown"),
                }
    files = []
    for key in keys:
        obj = objects[key]
        ref = linked.get(key)
        files.append({
            "key": key,
            "bytes": obj["bytes"],
            "story_id": ref["story_id"] if ref else None,
            "kind": ref["kind"] if ref else "unknown",
            "status": ref["status"] if ref else "unlinked",
            "can_delete": False,
            "reason": (
                "Файл защищён: нет подтверждённой политики хранения и "
                "транзакционной проверки заказа"
            ),
        })
    return {
        "bot_id": bot_id, "provider": provider, "files": files,
        "total_bytes": sum(file["bytes"] for file in files),
        "can_delete": False,
        "deletion_enabled": False,
        "message": "Это предварительная проверка, файлы не удалены.",
    }
