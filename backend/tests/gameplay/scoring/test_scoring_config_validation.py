import pytest

from app.gameplay.scoring import (
    COMPONENTS,
    MarginComponent,
    ScoringConfigError,
    WinnerComponent,
    validate_scoring_config,
)

WINNER_FLAT = {"enabled": True, "mode": "flat", "flat_points": 10.0}
MARGIN_POOL = {"enabled": True, "mode": "pool", "pool_points": 60.0}


def test_components_registry_holds_both_components_under_their_config_keys():
    assert set(COMPONENTS) == {"winner", "margin"}
    assert isinstance(COMPONENTS["winner"], WinnerComponent)
    assert isinstance(COMPONENTS["margin"], MarginComponent)


def test_accepts_a_valid_two_component_config():
    validate_scoring_config({"winner": WINNER_FLAT, "margin": MARGIN_POOL}, entry_count=6)


def test_accepts_an_empty_config():
    validate_scoring_config({}, entry_count=6)


def test_rejects_an_enabled_component_when_the_race_has_too_few_entries():
    # A single-entry time-trial heat: there is no "who won" to grade.
    with pytest.raises(ScoringConfigError, match="winner: not eligible"):
        validate_scoring_config({"winner": WINNER_FLAT}, entry_count=1)


def test_rejects_an_enabled_margin_component_when_the_race_has_too_few_entries():
    with pytest.raises(ScoringConfigError, match="margin: not eligible"):
        validate_scoring_config({"margin": MARGIN_POOL}, entry_count=1)


def test_a_disabled_component_is_skipped_entirely_including_its_eligibility_check():
    # Invalid config AND an ineligible race, but disabled -- so neither is checked.
    validate_scoring_config({"winner": {"enabled": False, "mode": "nonsense"}}, entry_count=1)


def test_a_component_absent_from_the_config_is_skipped():
    validate_scoring_config({"margin": MARGIN_POOL}, entry_count=2)


def test_rejects_an_invalid_enabled_component_config():
    with pytest.raises(ScoringConfigError, match="'flat_points'"):
        validate_scoring_config({"winner": {"enabled": True, "mode": "flat"}}, entry_count=4)


@pytest.mark.parametrize("bad_value", ["on", 1, True, ["enabled"]])
def test_rejects_a_component_config_that_is_not_an_object(bad_value):
    """scoring_config is caller-supplied JSON with no nested schema (PredictionMarketCreate's
    scoring_config field is a bare `dict`), so a truthy non-dict value for a component key
    (e.g. {"winner": "on"}) must be rejected as a clean ScoringConfigError -- not crash with
    an unhandled AttributeError/TypeError from treating it as a dict downstream."""
    with pytest.raises(ScoringConfigError, match="winner: component config must be an object"):
        validate_scoring_config({"winner": bad_value}, entry_count=4)


def test_margin_per_market_reads_typical_margin_seconds_from_the_top_level_config():
    """typical_margin_seconds lives at the top of scoring_config, not inside the margin slice
    -- validation has to inject it before handing the slice to the component."""
    validate_scoring_config(
        {
            "margin": {
                "enabled": True,
                "mode": "flat",
                "flat_base": 5.0,
                "m_source": "per_market",
            },
            "typical_margin_seconds": 6.0,
        },
        entry_count=4,
    )


def test_margin_per_market_is_rejected_when_the_top_level_typical_margin_is_missing():
    with pytest.raises(ScoringConfigError, match="'typical_margin_seconds'"):
        validate_scoring_config(
            {
                "margin": {
                    "enabled": True,
                    "mode": "flat",
                    "flat_base": 5.0,
                    "m_source": "per_market",
                }
            },
            entry_count=4,
        )


def test_margin_global_needs_no_top_level_typical_margin():
    validate_scoring_config(
        {
            "margin": {
                "enabled": True,
                "mode": "flat",
                "flat_base": 5.0,
                "m_source": "global",
            }
        },
        entry_count=4,
    )
