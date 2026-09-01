"""Shared pieces of the scoring-component framework: the component interface, the
winner-derivation helper both components need, and the error types callers catch."""

from abc import ABC, abstractmethod

from app.gameplay.models import Prediction, RaceEntry


class ScoringConfigError(ValueError):
    """A market's scoring_config is invalid, or an enabled component isn't eligible for the
    race it's attached to.

    A dedicated type rather than a bare ValueError so the endpoint layer (a later issue) can
    translate exactly these into a 422 without also swallowing an unrelated ValueError raised
    by a genuine bug."""


class ScoringPayloadError(ValueError):
    """A submitted prediction doesn't match what the market's scoring_config requires."""


def find_winner(race_entries: list[RaceEntry]) -> RaceEntry | None:
    """The finishing entry with the lowest time, or None if nobody finished.

    An entry only counts if it both has status "finished" and has a recorded time -- a
    finished entry whose time was never entered can't be ranked. An exact tie is deliberately
    not special-cased: real race data always resolves to a single winner, so no arbitrary
    tie-break rule is baked in here."""
    finishers = [
        entry for entry in race_entries if entry.status == "finished" and entry.time is not None
    ]
    if not finishers:
        return None
    return min(finishers, key=lambda entry: entry.time)


def require_mode(config: dict, component: str) -> str:
    """The component's payout mode, or ScoringConfigError if it isn't one of the two valid
    values. Both current components share this same flat/pool choice."""
    mode = config.get("mode")
    if mode not in ("flat", "pool"):
        raise ScoringConfigError(f"{component}: 'mode' must be 'flat' or 'pool', got {mode!r}")
    return mode


def require_positive_number(config: dict, key: str, component: str) -> float:
    """A strictly-positive numeric config value, or ScoringConfigError.

    bool is excluded explicitly: isinstance(True, int) is True in Python, so without the
    guard a `True` would sail through as the number 1."""
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ScoringConfigError(
            f"{component}: {key!r} must be a number greater than 0, got {value!r}"
        )
    return float(value)


class ScoringComponent(ABC):
    """One independent, self-contained scoring rule that a market's scoring_config can
    switch on.

    Every method receives only this component's own slice of the market config -- never the
    whole scoring_config -- so a component stays testable against a small standalone dict.
    The orchestration in this package's __init__ is responsible for carving out that slice
    (and for injecting any top-level key a component needs)."""

    #: Key this component occupies in a market's scoring_config, and its name in error messages.
    name: str

    def is_eligible(self, entry_count: int) -> bool:
        """Whether this component can be graded at all for a race with this many entries.

        Concrete on the base rather than abstract because both current components share the
        rule: you need at least two entries for "who won" or "by how much" to mean anything.
        (Margin only ever looks at the top two finishing times, so field size beyond two makes
        no difference to it.) A future component with a different rule overrides this."""
        return entry_count >= 2

    @abstractmethod
    def validate_market_config(self, config: dict) -> None:
        """Raise ScoringConfigError if this component's config slice is not usable."""

    @abstractmethod
    def validate_prediction_payload(self, config: dict, payload: dict) -> None:
        """Raise ScoringPayloadError if a submitted prediction doesn't satisfy what this
        component's config requires of it."""

    @abstractmethod
    def settle(
        self,
        config: dict,
        predictions: list[Prediction],
        race_entries: list[RaceEntry],
    ) -> dict[int, float]:
        """Points earned from THIS component alone, keyed by prediction id.

        Every passed prediction appears in the result, at 0.0 if it earned nothing -- callers
        never have to distinguish "scored zero" from "missing"."""
