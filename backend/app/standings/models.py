"""Response schema(s) for app.standings -- see app/standings/router.py's module docstring
for why this package exists."""

from sqlmodel import SQLModel


class LeagueStandingRead(SQLModel):
    """One row of GET /leagues/{league_id}/standings -- a league member and their
    season-to-date settled prediction points. Unlike a table's *Read class, this is not
    the public shape of a single table: it pairs league membership (app.leagues) with
    aggregated prediction points (app.gameplay), which is exactly why it lives in
    app.standings instead of either domain.

    `username` mirrors User.username's nullability rather than asserting non-null. In
    practice a member always has one, since every path into a league is gated on
    require_username -- but the column itself is nullable and the response type should not
    claim an invariant the database does not enforce."""

    user_id: int
    username: str | None
    points: float
