"""The winner component: pick which team wins the race."""

from app.gameplay.models import Prediction, RaceEntry
from app.gameplay.scoring.base import (
    ScoringComponent,
    find_winner,
    require_mode,
    require_positive_number,
)


class WinnerComponent(ScoringComponent):
    """Pays out on correctly picking the race's winner.

    Config: {"enabled": bool, "mode": "flat" | "pool", ...}
      - "flat" pays every correct picker "flat_points".
      - "pool" splits "pool_points" equally among all correct pickers."""

    name = "winner"

    def validate_market_config(self, config: dict) -> None:
        if require_mode(config, self.name) == "flat":
            require_positive_number(config, "flat_points", self.name)
        else:
            require_positive_number(config, "pool_points", self.name)

    def validate_prediction_payload(self, config: dict, payload: dict) -> None:
        """No-op, deliberately.

        picked_team_id is non-nullable on the Prediction model and required regardless of
        scoring config (it gates the margin component too), so there is nothing this
        component needs to check that depends on the config."""

    def settle(
        self,
        config: dict,
        predictions: list[Prediction],
        race_entries: list[RaceEntry],
    ) -> dict[int, float]:
        points = {prediction.id: 0.0 for prediction in predictions}

        winner = find_winner(race_entries)
        if winner is None:
            return points

        # A pick on a team that dnf'd/dns'd/dq'd needs no special case: that team can't be the
        # winner, so the pick simply doesn't match.
        correct = [
            prediction for prediction in predictions if prediction.picked_team_id == winner.team_id
        ]
        if not correct:
            # Zero correct pickers is a legitimate outcome, not an error and not a void.
            return points

        if config["mode"] == "flat":
            payout = float(config["flat_points"])
        else:
            payout = float(config["pool_points"]) / len(correct)

        for prediction in correct:
            points[prediction.id] = payout
        return points
