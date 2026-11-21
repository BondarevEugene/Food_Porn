"""Read-only selection preflight never authorizes cloud object deletion."""
import pytest

from app.crm.storage_preflight import inspect_selection


def inventory(status="ok"):
    return {
        "providers": [{
            "bot_id": "little_legend", "provider": "release",
            "status": status, "truncated": False,
            "objects": [{"key": "little-legend/books/1.pdf", "bytes": 25}],
        }],
        "books": [{
            "story_id": 7,
            "files": [{
                "provider": "release", "key": "little-legend/books/1.pdf",
                "kind": "pdf", "status": "ready",
            }],
        }],
    }


def test_known_paid_artifact_remains_protected():
    result = inspect_selection(
        inventory(), bot_id="little_legend", provider="release",
        keys=["little-legend/books/1.pdf"],
    )
    assert result["total_bytes"] == 25
    assert result["files"][0]["story_id"] == 7
    assert result["files"][0]["can_delete"] is False
    assert result["can_delete"] is False


def test_unknown_object_is_protected():
    data = inventory()
    data["books"] = []
    result = inspect_selection(
        data, bot_id="little_legend", provider="release",
        keys=["little-legend/books/1.pdf"],
    )
    assert result["files"][0]["status"] == "unlinked"
    assert result["can_delete"] is False


@pytest.mark.parametrize("keys", [[], ["x", "x"], ["x"] * 101])
def test_rejects_invalid_selection(keys):
    with pytest.raises(ValueError):
        inspect_selection(inventory(), bot_id="little_legend", provider="release", keys=keys)


def test_rejects_incomplete_or_mismatched_inventory():
    with pytest.raises(ValueError):
        inspect_selection(
            inventory("partial"), bot_id="little_legend", provider="release",
            keys=["little-legend/books/1.pdf"],
        )
    with pytest.raises(ValueError):
        inspect_selection(
            inventory(), bot_id="other_bot", provider="release",
            keys=["little-legend/books/1.pdf"],
        )
