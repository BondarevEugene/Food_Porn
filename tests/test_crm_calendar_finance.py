"""Calendar-period boundaries and CRM finance API contracts."""
from datetime import UTC

import pytest

from app.crm.service import calendar_bounds


@pytest.mark.parametrize(
    ("period", "year", "index", "start", "end"),
    [
        ("month", 2026, 11, "2026-11-01", "2026-12-01"),
        ("month", 2026, 12, "2026-12-01", "2027-01-01"),
        ("quarter", 2026, 4, "2026-10-01", "2027-01-01"),
        ("half", 2026, 2, "2026-07-01", "2027-01-01"),
        ("year", 2026, 1, "2026-01-01", "2027-01-01"),
        ("month", 2024, 2, "2024-02-01", "2024-03-01"),
    ],
)
def test_calendar_bounds(period, year, index, start, end):
    begin, finish = calendar_bounds(period, year, index)
    assert begin.date().isoformat() == start
    assert finish.date().isoformat() == end
    assert begin.tzinfo == UTC
    assert finish.tzinfo == UTC
    assert begin < finish


@pytest.mark.parametrize(
    ("period", "year", "index"),
    [
        ("week", 2026, 1),
        ("month", 2026, 13),
        ("quarter", 2026, 5),
        ("half", 2026, 3),
        ("year", 2026, 2),
        ("month", 1999, 1),
        ("month", 2101, 1),
    ],
)
def test_calendar_bounds_reject_invalid_periods(period, year, index):
    with pytest.raises(ValueError):
        calendar_bounds(period, year, index)
