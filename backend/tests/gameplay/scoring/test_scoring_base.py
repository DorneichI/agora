import pytest

from app.gameplay.models import RaceEntry
from app.gameplay.scoring.base import (
    ScoringConfigError,
    find_winner,
    require_mode,
    require_positive_number,
)


def _entry(entry_id, team_id, time, status="finished"):
    return RaceEntry(
        id=entry_id,
        race_id=1,
        team_id=team_id,
        level="varsity",
        time=time,
        status=status,
        created_by=1,
    )


def test_find_winner_returns_lowest_time_among_finishers():
    entries = [
        _entry(1, 10, 400.5),
        _entry(2, 20, 398.2),
        _entry(3, 30, 402.0),
    ]

    winner = find_winner(entries)

    assert winner is not None
    assert winner.team_id == 20


def test_find_winner_ignores_non_finished_entries_even_with_faster_times():
    entries = [
        _entry(1, 10, 400.5),
        _entry(2, 20, 350.0, status="dq"),
        _entry(3, 30, 360.0, status="dnf"),
    ]

    winner = find_winner(entries)

    assert winner is not None
    assert winner.team_id == 10


def test_find_winner_ignores_finished_entry_with_no_recorded_time():
    entries = [_entry(1, 10, None), _entry(2, 20, 400.0)]

    winner = find_winner(entries)

    assert winner is not None
    assert winner.team_id == 20


def test_find_winner_returns_none_when_nobody_finished():
    entries = [_entry(1, 10, None, status="dns"), _entry(2, 20, 400.0, status="dnf")]

    assert find_winner(entries) is None


def test_find_winner_returns_none_for_no_entries():
    assert find_winner([]) is None


def test_require_mode_accepts_flat_and_pool():
    assert require_mode({"mode": "flat"}, "winner") == "flat"
    assert require_mode({"mode": "pool"}, "winner") == "pool"


@pytest.mark.parametrize("config", [{}, {"mode": None}, {"mode": "parimutuel"}])
def test_require_mode_rejects_anything_else(config):
    with pytest.raises(ScoringConfigError, match="'mode' must be 'flat' or 'pool'"):
        require_mode(config, "winner")


def test_require_positive_number_returns_value_as_float():
    assert require_positive_number({"flat_points": 10}, "flat_points", "winner") == 10.0


@pytest.mark.parametrize(
    "value",
    [None, 0, -1, "10", True, float("nan"), float("inf"), float("-inf")],
)
def test_require_positive_number_rejects_non_positive_and_non_numbers(value):
    """NaN and +-Infinity are deliberately included alongside the non-numeric/non-positive
    cases: every comparison with float('nan') is False, and inf/-inf both fail a bare
    `value <= 0` check too, so without an explicit finiteness check either would otherwise
    sail through as if it were a valid positive number -- silently corrupting any later
    arithmetic built on it (e.g. a settled Prediction.points_awarded ending up NaN)."""
    with pytest.raises(ScoringConfigError, match="'flat_points' must be a number greater than 0"):
        require_positive_number({"flat_points": value}, "flat_points", "winner")


def test_require_positive_number_rejects_missing_key():
    with pytest.raises(ScoringConfigError, match="'flat_points' must be a number greater than 0"):
        require_positive_number({}, "flat_points", "winner")
