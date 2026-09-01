import pytest

from app.gameplay.models import Prediction, RaceEntry
from app.gameplay.scoring.base import ScoringConfigError
from app.gameplay.scoring.winner import WinnerComponent


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


def _prediction(prediction_id, picked_team_id):
    return Prediction(
        id=prediction_id,
        market_id=1,
        user_id=prediction_id,
        picked_team_id=picked_team_id,
    )


FLAT = {"enabled": True, "mode": "flat", "flat_points": 10.0}
POOL = {"enabled": True, "mode": "pool", "pool_points": 100.0}

# Team 20 wins at 398.2; team 10 is second; team 30 did not finish.
ENTRIES = [_entry(1, 10, 400.5), _entry(2, 20, 398.2), _entry(3, 30, None, status="dnf")]


def test_is_eligible_requires_at_least_two_entries():
    component = WinnerComponent()

    assert component.is_eligible(2) is True
    assert component.is_eligible(5) is True
    assert component.is_eligible(1) is False
    assert component.is_eligible(0) is False


def test_flat_mode_pays_every_correct_pick_the_full_amount():
    predictions = [_prediction(1, 20), _prediction(2, 20), _prediction(3, 10)]

    points = WinnerComponent().settle(FLAT, predictions, ENTRIES)

    assert points == {1: 10.0, 2: 10.0, 3: 0.0}


def test_incorrect_pick_scores_zero():
    predictions = [_prediction(1, 10)]

    assert WinnerComponent().settle(FLAT, predictions, ENTRIES) == {1: 0.0}


def test_pick_on_a_team_that_did_not_finish_scores_zero():
    predictions = [_prediction(1, 30)]

    assert WinnerComponent().settle(FLAT, predictions, ENTRIES) == {1: 0.0}


def test_pool_mode_splits_the_pool_equally_among_correct_pickers():
    predictions = [_prediction(1, 20), _prediction(2, 20), _prediction(3, 20), _prediction(4, 10)]

    points = WinnerComponent().settle(POOL, predictions, ENTRIES)

    assert points[1] == pytest.approx(100.0 / 3)
    assert points[2] == pytest.approx(100.0 / 3)
    assert points[3] == pytest.approx(100.0 / 3)
    assert points[4] == 0.0


def test_pool_mode_gives_a_single_correct_picker_the_whole_pool():
    predictions = [_prediction(1, 20), _prediction(2, 10)]

    assert WinnerComponent().settle(POOL, predictions, ENTRIES) == {1: 100.0, 2: 0.0}


def test_pool_mode_with_zero_correct_pickers_pays_nothing_without_erroring():
    predictions = [_prediction(1, 10), _prediction(2, 30)]

    assert WinnerComponent().settle(POOL, predictions, ENTRIES) == {1: 0.0, 2: 0.0}


def test_settle_returns_all_zero_when_nobody_finished():
    entries = [_entry(1, 10, None, status="dnf"), _entry(2, 20, None, status="dns")]
    predictions = [_prediction(1, 10), _prediction(2, 20)]

    assert WinnerComponent().settle(FLAT, predictions, entries) == {1: 0.0, 2: 0.0}


def test_validate_market_config_accepts_valid_flat_and_pool():
    WinnerComponent().validate_market_config(FLAT)
    WinnerComponent().validate_market_config(POOL)


def test_validate_market_config_rejects_flat_without_positive_points():
    with pytest.raises(ScoringConfigError, match="'flat_points'"):
        WinnerComponent().validate_market_config({"enabled": True, "mode": "flat"})


def test_validate_market_config_rejects_pool_without_positive_points():
    with pytest.raises(ScoringConfigError, match="'pool_points'"):
        WinnerComponent().validate_market_config(
            {"enabled": True, "mode": "pool", "pool_points": 0}
        )


def test_validate_market_config_rejects_unknown_mode():
    with pytest.raises(ScoringConfigError, match="'mode'"):
        WinnerComponent().validate_market_config({"enabled": True, "mode": "kalshi"})


def test_validate_prediction_payload_never_raises():
    """picked_team_id is required on every Prediction regardless of config, so this component
    has nothing config-dependent to check."""
    WinnerComponent().validate_prediction_payload(FLAT, {})
    WinnerComponent().validate_prediction_payload({"enabled": False}, {"picked_team_id": 1})
