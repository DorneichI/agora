import sys

import pytest

from app.gameplay.models import Prediction, RaceEntry
from app.gameplay.scoring.base import ScoringConfigError, ScoringPayloadError
from app.gameplay.scoring.margin import DEFAULT_TYPICAL_MARGIN_SECONDS, MarginComponent


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


def _prediction(prediction_id, picked_team_id, margin_threshold_seconds=None):
    return Prediction(
        id=prediction_id,
        market_id=1,
        user_id=prediction_id,
        picked_team_id=picked_team_id,
        margin_threshold_seconds=margin_threshold_seconds,
    )


FLAT_GLOBAL = {
    "enabled": True,
    "mode": "flat",
    "flat_base": 5.0,
    "m_source": "global",
    "typical_margin_seconds": None,
}
FLAT_PER_MARKET = {
    "enabled": True,
    "mode": "flat",
    "flat_base": 5.0,
    "m_source": "per_market",
    "typical_margin_seconds": 6.0,
}
POOL = {
    "enabled": True,
    "mode": "pool",
    "pool_points": 60.0,
    "typical_margin_seconds": None,
}

# Team 20 wins at 396.0, team 10 second at 400.0 -> actual margin is 4.0s. Team 30 dnf'd.
ENTRIES = [_entry(1, 10, 400.0), _entry(2, 20, 396.0), _entry(3, 30, None, status="dnf")]


def test_default_typical_margin_seconds_is_the_documented_placeholder():
    assert DEFAULT_TYPICAL_MARGIN_SECONDS == 3.0


def test_is_eligible_requires_at_least_two_entries():
    component = MarginComponent()

    assert component.is_eligible(2) is True
    assert component.is_eligible(1) is False


def test_flat_global_pays_base_times_two_to_the_threshold_over_global_m():
    # Threshold 3.0 < actual margin 4.0 -> covered. M is the global 3.0, so 5 * 2**1 == 10.
    predictions = [_prediction(1, 20, 3.0)]

    points = MarginComponent().settle(FLAT_GLOBAL, predictions, ENTRIES)

    assert points[1] == pytest.approx(5.0 * 2 ** (3.0 / DEFAULT_TYPICAL_MARGIN_SECONDS))
    assert points[1] == pytest.approx(10.0)


def test_flat_per_market_uses_the_markets_own_m_not_the_global_one():
    # Same threshold, but M is 6.0 here, so the payout is 5 * 2**0.5, not 5 * 2**1.
    predictions = [_prediction(1, 20, 3.0)]

    points = MarginComponent().settle(FLAT_PER_MARKET, predictions, ENTRIES)

    assert points[1] == pytest.approx(5.0 * 2 ** (3.0 / 6.0))
    assert points[1] != pytest.approx(5.0 * 2 ** (3.0 / DEFAULT_TYPICAL_MARGIN_SECONDS))


def test_flat_mode_clamps_to_max_float_instead_of_overflowing_on_extreme_threshold():
    """margin_threshold_seconds is only bounded below (> 0), and RaceEntry.time has no upper
    bound either -- a race with an extreme recorded time gap (e.g. a data-entry error) paired
    with an almost-as-extreme, still-covered threshold pushes 2**(threshold/M) past float64's
    range. Settlement must clamp to the largest finite float instead of letting an
    OverflowError crash settlement for every prediction on the market."""
    entries = [_entry(1, 10, 1e9), _entry(2, 20, 0.0)]
    # Covered: actual margin (1e9 - 0.0 == 1e9) > threshold (5e8).
    predictions = [_prediction(1, 20, 5e8)]

    points = MarginComponent().settle(FLAT_GLOBAL, predictions, entries)

    assert points[1] == sys.float_info.max


def test_a_bolder_threshold_pays_more_in_flat_mode():
    predictions = [_prediction(1, 20, 1.0), _prediction(2, 20, 3.9)]

    points = MarginComponent().settle(FLAT_GLOBAL, predictions, ENTRIES)

    assert points[2] > points[1]


def test_uncovered_threshold_scores_zero():
    # Threshold 4.0 is not strictly less than the actual margin of 4.0 -- coverage requires
    # actual > threshold.
    predictions = [_prediction(1, 20, 4.0), _prediction(2, 20, 9.0)]

    assert MarginComponent().settle(FLAT_GLOBAL, predictions, ENTRIES) == {1: 0.0, 2: 0.0}


def test_wrong_winner_pick_scores_zero_even_when_the_threshold_was_covered():
    predictions = [_prediction(1, 10, 1.0), _prediction(2, 30, 1.0)]

    assert MarginComponent().settle(FLAT_GLOBAL, predictions, ENTRIES) == {1: 0.0, 2: 0.0}


def test_pool_mode_splits_equally_among_covered_ignoring_how_bold_each_was():
    # Both covered (1.0 and 3.9 are under the 4.0 actual margin); the bolder one gets no
    # larger share. The third is winner-correct but uncovered, the fourth picked wrong.
    predictions = [
        _prediction(1, 20, 1.0),
        _prediction(2, 20, 3.9),
        _prediction(3, 20, 9.0),
        _prediction(4, 10, 1.0),
    ]

    points = MarginComponent().settle(POOL, predictions, ENTRIES)

    assert points[1] == pytest.approx(30.0)
    assert points[2] == pytest.approx(30.0)
    assert points[3] == 0.0
    assert points[4] == 0.0


def test_pool_mode_with_zero_covered_predictions_pays_nothing_without_erroring():
    predictions = [_prediction(1, 20, 9.0), _prediction(2, 10, 1.0)]

    assert MarginComponent().settle(POOL, predictions, ENTRIES) == {1: 0.0, 2: 0.0}


def test_margin_voids_when_fewer_than_two_entries_finished():
    # Only one finisher, so there is no runner-up time and no margin to compute. Nobody is
    # paid, and nobody is treated as having missed.
    entries = [_entry(1, 10, 400.0), _entry(2, 20, None, status="dnf")]
    predictions = [_prediction(1, 10, 1.0), _prediction(2, 20, 1.0)]

    assert MarginComponent().settle(FLAT_GLOBAL, predictions, entries) == {1: 0.0, 2: 0.0}


def test_margin_voids_when_nobody_finished():
    entries = [_entry(1, 10, None, status="dns"), _entry(2, 20, None, status="dnf")]
    predictions = [_prediction(1, 10, 1.0)]

    assert MarginComponent().settle(FLAT_GLOBAL, predictions, entries) == {1: 0.0}


def test_margin_uses_the_top_two_finishing_times_regardless_of_field_size():
    # Six boats; only the gap between the two fastest matters (396.0 -> 400.0 == 4.0s).
    entries = [
        _entry(1, 10, 400.0),
        _entry(2, 20, 396.0),
        _entry(3, 30, 410.0),
        _entry(4, 40, 420.0),
        _entry(5, 50, 430.0),
        _entry(6, 60, 440.0),
    ]
    predictions = [_prediction(1, 20, 3.9), _prediction(2, 20, 4.1)]

    points = MarginComponent().settle(FLAT_GLOBAL, predictions, entries)

    assert points[1] > 0.0
    assert points[2] == 0.0


def test_validate_market_config_accepts_valid_configs():
    MarginComponent().validate_market_config(FLAT_GLOBAL)
    MarginComponent().validate_market_config(FLAT_PER_MARKET)
    MarginComponent().validate_market_config(POOL)


def test_validate_market_config_rejects_flat_without_positive_base():
    with pytest.raises(ScoringConfigError, match="'flat_base'"):
        MarginComponent().validate_market_config(
            {"enabled": True, "mode": "flat", "m_source": "global"}
        )


def test_validate_market_config_rejects_flat_with_unknown_m_source():
    with pytest.raises(ScoringConfigError, match="'m_source'"):
        MarginComponent().validate_market_config(
            {"enabled": True, "mode": "flat", "flat_base": 5.0, "m_source": "per_league"}
        )


def test_validate_market_config_rejects_per_market_without_typical_margin_seconds():
    with pytest.raises(ScoringConfigError, match="'typical_margin_seconds'"):
        MarginComponent().validate_market_config(
            {
                "enabled": True,
                "mode": "flat",
                "flat_base": 5.0,
                "m_source": "per_market",
                "typical_margin_seconds": None,
            }
        )


def test_validate_market_config_pool_needs_no_m_source_or_typical_margin():
    """Pool payouts ignore how bold a threshold was, so they need no M at all."""
    MarginComponent().validate_market_config({"enabled": True, "mode": "pool", "pool_points": 60.0})


def test_validate_market_config_rejects_pool_without_positive_points():
    with pytest.raises(ScoringConfigError, match="'pool_points'"):
        MarginComponent().validate_market_config({"enabled": True, "mode": "pool"})


def test_validate_prediction_payload_requires_a_positive_threshold_when_enabled():
    MarginComponent().validate_prediction_payload(FLAT_GLOBAL, {"margin_threshold_seconds": 2.5})


@pytest.mark.parametrize(
    "threshold", [None, 0, -1.0, "2.5", True, float("nan"), float("inf"), float("-inf")]
)
def test_validate_prediction_payload_rejects_bad_threshold_when_enabled(threshold):
    with pytest.raises(ScoringPayloadError, match="margin_threshold_seconds is required"):
        MarginComponent().validate_prediction_payload(
            FLAT_GLOBAL, {"margin_threshold_seconds": threshold}
        )


def test_validate_prediction_payload_rejects_a_missing_threshold_when_enabled():
    with pytest.raises(ScoringPayloadError, match="margin_threshold_seconds is required"):
        MarginComponent().validate_prediction_payload(FLAT_GLOBAL, {})


def test_validate_prediction_payload_rejects_a_threshold_when_disabled():
    with pytest.raises(ScoringPayloadError, match="must be omitted"):
        MarginComponent().validate_prediction_payload(
            {"enabled": False}, {"margin_threshold_seconds": 2.5}
        )


def test_validate_prediction_payload_accepts_no_threshold_when_disabled():
    MarginComponent().validate_prediction_payload({"enabled": False}, {})
    MarginComponent().validate_prediction_payload(
        {"enabled": False}, {"margin_threshold_seconds": None}
    )
