import pytest

from app.gameplay.models import Prediction, PredictionMarket, RaceEntry
from app.gameplay.scoring import DEFAULT_TYPICAL_MARGIN_SECONDS, settle_market


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


def _market(scoring_config):
    return PredictionMarket(id=1, race_id=1, scoring_config=scoring_config, created_by=1)


WINNER_FLAT = {"enabled": True, "mode": "flat", "flat_points": 10.0}
MARGIN_FLAT_GLOBAL = {
    "enabled": True,
    "mode": "flat",
    "flat_base": 5.0,
    "m_source": "global",
}

# Team 20 wins at 396.0, team 10 second at 400.0 -> actual margin 4.0s. Team 30 dnf'd.
ENTRIES = [_entry(1, 10, 400.0), _entry(2, 20, 396.0), _entry(3, 30, None, status="dnf")]


def test_totals_are_summed_across_both_components():
    market = _market({"winner": WINNER_FLAT, "margin": MARGIN_FLAT_GLOBAL})
    # Correct winner AND covered margin (3.0 < 4.0): 10 from winner, 5 * 2**1 from margin.
    predictions = [_prediction(1, 20, 3.0)]

    totals = settle_market(market, predictions, ENTRIES)

    assert totals[1] == pytest.approx(10.0 + 5.0 * 2 ** (3.0 / DEFAULT_TYPICAL_MARGIN_SECONDS))
    assert totals[1] == pytest.approx(20.0)


def test_correct_winner_with_an_uncovered_margin_still_earns_the_winner_points():
    market = _market({"winner": WINNER_FLAT, "margin": MARGIN_FLAT_GLOBAL})
    predictions = [_prediction(1, 20, 9.0)]

    assert settle_market(market, predictions, ENTRIES) == {1: 10.0}


def test_margin_only_market_pays_nothing_to_a_wrong_winner_pick():
    """The winner component being disabled doesn't stop margin from requiring a correct
    winner pick."""
    market = _market({"margin": MARGIN_FLAT_GLOBAL})
    predictions = [_prediction(1, 10, 1.0)]

    assert settle_market(market, predictions, ENTRIES) == {1: 0.0}


def test_margin_voids_but_winner_points_are_still_awarded():
    # Only one finisher: no runner-up, so no margin. The winner is still unambiguous.
    entries = [_entry(1, 10, 400.0), _entry(2, 20, None, status="dnf")]
    market = _market({"winner": WINNER_FLAT, "margin": MARGIN_FLAT_GLOBAL})
    predictions = [_prediction(1, 10, 1.0), _prediction(2, 20, 1.0)]

    assert settle_market(market, predictions, entries) == {1: 10.0, 2: 0.0}


def test_whole_market_voids_when_no_entry_finished():
    entries = [_entry(1, 10, None, status="dnf"), _entry(2, 20, None, status="dns")]
    market = _market({"winner": WINNER_FLAT, "margin": MARGIN_FLAT_GLOBAL})
    predictions = [_prediction(1, 10, 1.0), _prediction(2, 20, 1.0)]

    assert settle_market(market, predictions, entries) == {1: 0.0, 2: 0.0}


def test_every_prediction_appears_in_the_result_even_at_zero():
    market = _market({"winner": WINNER_FLAT})
    predictions = [_prediction(1, 20), _prediction(2, 10), _prediction(3, 30)]

    totals = settle_market(market, predictions, ENTRIES)

    assert set(totals) == {1, 2, 3}
    assert totals == {1: 10.0, 2: 0.0, 3: 0.0}


def test_a_disabled_component_contributes_nothing():
    market = _market({"winner": WINNER_FLAT, "margin": {**MARGIN_FLAT_GLOBAL, "enabled": False}})
    predictions = [_prediction(1, 20, 3.0)]

    assert settle_market(market, predictions, ENTRIES) == {1: 10.0}


def test_an_empty_scoring_config_pays_nothing():
    market = _market({})
    predictions = [_prediction(1, 20)]

    assert settle_market(market, predictions, ENTRIES) == {1: 0.0}


def test_no_predictions_returns_an_empty_mapping():
    market = _market({"winner": WINNER_FLAT})

    assert settle_market(market, [], ENTRIES) == {}


def test_per_market_typical_margin_is_injected_into_the_margin_component():
    market = _market(
        {
            "margin": {
                "enabled": True,
                "mode": "flat",
                "flat_base": 5.0,
                "m_source": "per_market",
            },
            "typical_margin_seconds": 6.0,
        }
    )
    predictions = [_prediction(1, 20, 3.0)]

    totals = settle_market(market, predictions, ENTRIES)

    assert totals[1] == pytest.approx(5.0 * 2 ** (3.0 / 6.0))


def test_pool_components_split_across_predictions_and_sum_per_prediction():
    market = _market(
        {
            "winner": {"enabled": True, "mode": "pool", "pool_points": 100.0},
            "margin": {"enabled": True, "mode": "pool", "pool_points": 60.0},
        }
    )
    # Predictions 1 and 2 both pick the winner; only 1 is covered (1.0 < 4.0, 9.0 is not).
    predictions = [_prediction(1, 20, 1.0), _prediction(2, 20, 9.0), _prediction(3, 10, 1.0)]

    totals = settle_market(market, predictions, ENTRIES)

    assert totals[1] == pytest.approx(50.0 + 60.0)
    assert totals[2] == pytest.approx(50.0)
    assert totals[3] == 0.0
