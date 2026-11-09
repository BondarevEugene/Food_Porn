"""Regression tests for AI scene-plan normalization."""
import pytest

from app.services.goal_story import (
    normalize_scene_directions,
    repair_photo_pairing,
    valid_photo_pairing,
)


@pytest.mark.parametrize("photo_count", range(1, 8))
@pytest.mark.parametrize("goal_count", range(5, 10))
def test_repaired_pairing_covers_photos(photo_count, goal_count):
    raw = [0] * goal_count
    result = repair_photo_pairing(raw, photo_count, goal_count)
    assert valid_photo_pairing(result, photo_count, goal_count)
    assert len(result) == goal_count


@pytest.mark.parametrize("raw", [None, [], ["invalid"], [-1, 99], [True, False]])
def test_repaired_pairing_handles_invalid_ai_indices(raw):
    result = repair_photo_pairing(raw, 4, 7)
    assert valid_photo_pairing(result, 4, 7)


def test_repair_preserves_valid_assignments():
    raw = [0, 1, 2, 3, 4, 0, 1]
    assert repair_photo_pairing(raw, 5, 7) == tuple(raw)


def test_repair_keeps_earlier_valid_choices_where_possible():
    result = repair_photo_pairing([0, 0, 1, 2, 3, 0, 1], 5, 7)
    assert result[:5] == (0, 0, 1, 2, 3)
    assert 4 in result


def test_directions_keep_valid_text_and_replace_missing():
    result = normalize_scene_directions(["sunlit garden", "", 123], 5)
    assert len(result) == 5
    assert result[0] == "sunlit garden"
    assert all(isinstance(scene, str) and scene for scene in result)
    assert all(len(scene) <= 220 for scene in result)


def test_directions_reject_oversized_text():
    assert normalize_scene_directions(["x" * 221], 5)[0] != "x" * 221
