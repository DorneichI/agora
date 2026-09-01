"""Composable scoring for prediction markets.

A market's scoring_config switches on independent components rather than selecting one of a
fixed set of "systems", so a new prediction type can be added later without touching what's
already shipped. Adding one means adding its module plus one entry in COMPONENTS below.

Everything here is pure and in-memory: these functions take already-loaded objects and return
plain dicts. Reading from and writing to the database -- including persisting the result to
Prediction.points_awarded and stamping PredictionMarket.settled_at -- belongs to the
settlement endpoint, not to this package."""

from app.gameplay.models import Prediction, PredictionMarket, RaceEntry
from app.gameplay.scoring.base import (
    ScoringComponent,
    ScoringConfigError,
    ScoringPayloadError,
    find_winner,
)
from app.gameplay.scoring.margin import DEFAULT_TYPICAL_MARGIN_SECONDS, MarginComponent
from app.gameplay.scoring.winner import WinnerComponent

#: Every component the framework knows about, keyed by the name it occupies in a market's
#: scoring_config. Components are stateless, so one shared instance each is fine.
COMPONENTS: dict[str, ScoringComponent] = {
    "winner": WinnerComponent(),
    "margin": MarginComponent(),
}

__all__ = [
    "COMPONENTS",
    "DEFAULT_TYPICAL_MARGIN_SECONDS",
    "MarginComponent",
    "ScoringComponent",
    "ScoringConfigError",
    "ScoringPayloadError",
    "WinnerComponent",
    "find_winner",
    "settle_market",
    "validate_scoring_config",
]


def _effective_config(scoring_config: dict, name: str) -> dict:
    """One component's own slice of a market's scoring_config.

    "typical_margin_seconds" is stored at the top level of scoring_config rather than inside
    the margin slice, so it gets injected here. Doing it in one place keeps every component
    seeing only its own keys -- WinnerComponent is never handed margin's settings, and
    MarginComponent stays testable against a small standalone dict."""
    config = dict(scoring_config.get(name) or {})
    if name == "margin":
        config["typical_margin_seconds"] = scoring_config.get("typical_margin_seconds")
    return config


def _enabled_components(
    scoring_config: dict,
) -> list[tuple[str, ScoringComponent, dict]]:
    """Each enabled component with its name and effective config. A component that's absent
    or explicitly disabled is skipped entirely -- its config is never validated and its
    eligibility is never checked."""
    return [
        (name, component, _effective_config(scoring_config, name))
        for name, component in COMPONENTS.items()
        if (scoring_config.get(name) or {}).get("enabled")
    ]


def validate_scoring_config(config: dict, entry_count: int) -> None:
    """Check a whole scoring_config against the race it would be attached to.

    Raises ScoringConfigError if an enabled component can't be graded for a race with this
    many entries (e.g. a single-entry time-trial heat), or if its own config is malformed."""
    for name, component, component_config in _enabled_components(config):
        if not component.is_eligible(entry_count):
            raise ScoringConfigError(f"{name}: not eligible for a race with {entry_count} entries")
        component.validate_market_config(component_config)


def settle_market(
    market: PredictionMarket,
    predictions: list[Prediction],
    race_entries: list[RaceEntry],
) -> dict[int, float]:
    """Total points each prediction earns, summed across every enabled component.

    Every passed prediction appears in the result, at 0.0 if it earned nothing. If no entry
    finished at all the whole market voids: everyone gets 0.0 from every component, and it
    counts as a loss for nobody."""
    totals = {prediction.id: 0.0 for prediction in predictions}

    if find_winner(race_entries) is None:
        return totals

    for _name, component, component_config in _enabled_components(market.scoring_config):
        awarded = component.settle(component_config, predictions, race_entries)
        for prediction_id, points in awarded.items():
            totals[prediction_id] += points
    return totals
