"""The margin component: pick how big the winning margin will be."""

import sys

from app.gameplay.models import Prediction, RaceEntry
from app.gameplay.scoring.base import (
    ScoringComponent,
    ScoringConfigError,
    ScoringPayloadError,
    is_positive_finite_number,
    require_mode,
    require_positive_number,
    zero_totals_or_winner,
)

#: The global "typical winning margin" reference constant, in seconds -- the M in a flat
#: margin payout's `flat_base * 2 ** (threshold / M)`.
#:
#: PLACEHOLDER. This is not a tuned value: it was picked to be roughly plausible before any
#: real race-margin data existed. Revisit once enough results are recorded to know what a
#: typical winning margin actually looks like per boat class.
DEFAULT_TYPICAL_MARGIN_SECONDS = 3.0


class MarginComponent(ScoringComponent):
    """Pays out on correctly calling that the race was won by more than some threshold.

    Only ever pays when the winner pick was ALSO correct -- a margin call on the wrong boat
    is worth nothing.

    Config: {"enabled": bool, "mode": "flat" | "pool", ...}
      - "flat" pays a covered prediction `flat_base * 2 ** (threshold / M)`, so a bolder
        threshold is worth more. M comes from "m_source": "global" uses
        DEFAULT_TYPICAL_MARGIN_SECONDS, "per_market" uses the market's own
        "typical_margin_seconds" (injected into this slice by this package's __init__).
      - "pool" splits "pool_points" equally among every covered prediction, ignoring how bold
        each threshold was -- boldness decides whether you're in the covered group, not the
        size of your share. Pool mode therefore needs neither "m_source" nor
        "typical_margin_seconds"."""

    name = "margin"
    extra_top_level_keys = ("typical_margin_seconds",)

    def validate_market_config(self, config: dict) -> None:
        if require_mode(config, self.name) == "pool":
            require_positive_number(config, "pool_points", self.name)
            return

        require_positive_number(config, "flat_base", self.name)
        m_source = config.get("m_source")
        if m_source not in ("global", "per_market"):
            raise ScoringConfigError(
                f"{self.name}: 'm_source' must be 'global' or 'per_market', got {m_source!r}"
            )
        if m_source == "per_market":
            require_positive_number(config, "typical_margin_seconds", self.name)

    def validate_prediction_payload(self, config: dict, payload: dict) -> None:
        threshold = payload.get("margin_threshold_seconds")
        if config.get("enabled"):
            if not is_positive_finite_number(threshold):
                raise ScoringPayloadError(
                    "margin_threshold_seconds is required and must be a number greater than 0 "
                    "when the margin component is enabled"
                )
        elif threshold is not None:
            raise ScoringPayloadError(
                "margin_threshold_seconds must be omitted when the margin component is disabled"
            )

    def settle(
        self,
        config: dict,
        predictions: list[Prediction],
        race_entries: list[RaceEntry],
    ) -> dict[int, float]:
        """Assumes every prediction has a non-null margin_threshold_seconds -- guaranteed by
        validate_prediction_payload having run at submission time (the endpoint layer's job,
        a later issue). Settlement does not re-check it.

        winner is derived here rather than taken from WinnerComponent: margin has to know who
        won even when the winner component itself is disabled, so it can't depend on that
        component's output."""
        points, winner = zero_totals_or_winner(predictions, race_entries)
        if winner is None:
            return points

        finish_times = sorted(
            entry.time
            for entry in race_entries
            if entry.status == "finished" and entry.time is not None
        )
        if len(finish_times) < 2:
            # No runner-up means no margin to grade. This component voids for the whole
            # market: nobody is paid and nobody is counted as having missed. Winner-component
            # points are unaffected.
            return points

        actual_margin_seconds = finish_times[1] - finish_times[0]
        covered = [
            prediction
            for prediction in predictions
            if prediction.picked_team_id == winner.team_id
            and actual_margin_seconds > prediction.margin_threshold_seconds
        ]
        if not covered:
            # Zero covered predictions is a legitimate outcome, not a void.
            return points

        if config["mode"] == "pool":
            payout = float(config["pool_points"]) / len(covered)
            for prediction in covered:
                points[prediction.id] = payout
            return points

        m = (
            DEFAULT_TYPICAL_MARGIN_SECONDS
            if config["m_source"] == "global"
            else float(config["typical_margin_seconds"])
        )
        flat_base = float(config["flat_base"])
        for prediction in covered:
            try:
                points[prediction.id] = flat_base * 2 ** (prediction.margin_threshold_seconds / m)
            except OverflowError:
                # margin_threshold_seconds is only bounded below (> 0), not above, so an
                # extreme-but-otherwise-valid submitted threshold can push this exponential
                # payout formula past float64's range. Clamp to the largest finite float
                # instead of letting settlement crash for every prediction on the market --
                # this preserves "a bolder threshold pays more" (the clamp is still the
                # largest representable payout) without inventing a new rejection rule at
                # submission time.
                points[prediction.id] = sys.float_info.max
        return points
