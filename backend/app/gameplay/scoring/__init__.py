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
    zero_totals_or_winner,
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
    "settle_market",
    "validate_prediction_payload",
    "validate_scoring_config",
]


def _effective_config(scoring_config: dict, name: str) -> dict:
    """One component's own slice of a market's scoring_config, plus each of the component's
    own extra_top_level_keys injected in (e.g. margin's "typical_margin_seconds", which is
    stored at the top level of scoring_config rather than inside margin's own slice) -- read
    generically off the component itself (ScoringComponent.extra_top_level_keys) so adding a
    component with its own top-level key needs no change here, matching the module
    docstring's "adding one means adding its module plus one entry in COMPONENTS" promise.
    Doing this in one place also keeps every component seeing only its own keys --
    WinnerComponent is never handed margin's settings.

    scoring_config's per-component value is caller-supplied JSON (via PredictionMarketCreate's
    untyped `scoring_config: dict` field), so it is not guaranteed to actually be an object --
    raises ScoringConfigError if scoring_config[name] is present but not a dict, rather than
    silently treating it as one and crashing on the first .get() call downstream."""
    raw = scoring_config.get(name)
    if raw is not None and not isinstance(raw, dict):
        raise ScoringConfigError(f"{name}: component config must be an object, got {raw!r}")
    config = dict(raw or {})
    for key in COMPONENTS[name].extra_top_level_keys:
        config[key] = scoring_config.get(key)
    return config


def _enabled_components(
    scoring_config: dict,
) -> list[tuple[str, ScoringComponent, dict]]:
    """Each enabled component with its name and effective config. A component that's absent
    or explicitly disabled is skipped entirely -- its config is never validated and its
    eligibility is never checked."""
    enabled = []
    for name, component in COMPONENTS.items():
        component_config = _effective_config(scoring_config, name)
        if component_config.get("enabled"):
            enabled.append((name, component, component_config))
    return enabled


def validate_scoring_config(config: dict, entry_count: int) -> None:
    """Check a whole scoring_config against the race it would be attached to.

    Raises ScoringConfigError if an enabled component can't be graded for a race with this
    many entries (e.g. a single-entry time-trial heat), or if its own config is malformed."""
    for name, component, component_config in _enabled_components(config):
        if not component.is_eligible(entry_count):
            raise ScoringConfigError(f"{name}: not eligible for a race with {entry_count} entries")
        component.validate_market_config(component_config)


def validate_prediction_payload(scoring_config: dict, payload: dict) -> None:
    """Check a submitted prediction's payload against every component mentioned in the
    market's scoring_config -- whether that component is enabled or explicitly disabled.
    Unlike validate_scoring_config, a disabled component still runs its own
    validate_prediction_payload: that's what rejects a payload field that doesn't belong on
    a disabled component (e.g. margin_threshold_seconds when margin is off). A component
    absent from scoring_config entirely is skipped -- nothing was ever configured for it, so
    there's nothing to check the payload against.

    Raises ScoringPayloadError if any present component's requirement isn't met."""
    for name, component in COMPONENTS.items():
        if name not in scoring_config:
            continue
        component.validate_prediction_payload(_effective_config(scoring_config, name), payload)


def settle_market(
    market: PredictionMarket,
    predictions: list[Prediction],
    race_entries: list[RaceEntry],
) -> dict[int, float]:
    """Total points each prediction earns, summed across every enabled component.

    Every passed prediction appears in the result, at 0.0 if it earned nothing. If no entry
    finished at all the whole market voids: everyone gets 0.0 from every component, and it
    counts as a loss for nobody."""
    totals, winner = zero_totals_or_winner(predictions, race_entries)
    if winner is None:
        return totals

    for _name, component, component_config in _enabled_components(market.scoring_config):
        awarded = component.settle(component_config, predictions, race_entries)
        for prediction_id, points in awarded.items():
            totals[prediction_id] += points
    return totals
