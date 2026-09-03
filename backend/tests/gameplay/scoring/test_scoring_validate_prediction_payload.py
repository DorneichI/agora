import pytest

from app.gameplay.scoring import ScoringPayloadError, validate_prediction_payload

WINNER_FLAT = {"enabled": True, "mode": "flat", "flat_points": 10.0}
MARGIN_ENABLED = {"enabled": True, "mode": "pool", "pool_points": 60.0}
MARGIN_DISABLED = {"enabled": False}


def test_accepts_payload_when_margin_disabled_and_threshold_omitted():
    validate_prediction_payload(
        {"winner": WINNER_FLAT, "margin": MARGIN_DISABLED},
        {"margin_threshold_seconds": None},
    )


def test_accepts_payload_when_margin_enabled_and_threshold_present():
    validate_prediction_payload(
        {"margin": MARGIN_ENABLED},
        {"margin_threshold_seconds": 5.0},
    )


def test_rejects_payload_when_margin_enabled_and_threshold_omitted():
    with pytest.raises(ScoringPayloadError, match="margin_threshold_seconds is required"):
        validate_prediction_payload(
            {"margin": MARGIN_ENABLED},
            {"margin_threshold_seconds": None},
        )


def test_rejects_payload_when_margin_disabled_and_threshold_present():
    with pytest.raises(ScoringPayloadError, match="must be omitted"):
        validate_prediction_payload(
            {"margin": MARGIN_DISABLED},
            {"margin_threshold_seconds": 5.0},
        )


def test_accepts_any_payload_when_no_components_enabled():
    validate_prediction_payload({}, {"margin_threshold_seconds": 999.0})
