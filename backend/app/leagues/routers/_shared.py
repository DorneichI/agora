from sqlalchemy.exc import IntegrityError

# Postgres SQLSTATE for a unique-constraint violation.
UNIQUE_VIOLATION_SQLSTATE = "23505"


def is_membership_collision(exc: IntegrityError) -> bool:
    """Same reasoning as `_is_invite_code_collision` in invites.py, but for the partial
    unique index that guards against a duplicate active `LeagueUser` row (two concurrent
    join/redeem requests for the same user racing each other)."""
    cause = getattr(exc.orig, "__cause__", None)
    return (
        getattr(cause, "sqlstate", None) == UNIQUE_VIOLATION_SQLSTATE
        and getattr(cause, "constraint_name", None) == "ix_leagueuser_league_id_user_id_active"
    )
