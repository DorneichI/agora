"""Regression guard for backend/CLAUDE.md's authorization convention: "Gate a route to
admins only with Depends(require_admin) ... rather than checking user.role inline in the
route body."

Deny-by-default: every mutating (non-GET) route must depend on require_admin *unless* it's
in the explicit exemption list below, rather than only checking routes on an allowlist --
an allowlist-only check would silently skip a brand new mutating route that forgets
`Depends(require_admin)`, which defeats the point of a regression guard. This walks the
actual FastAPI route table instead of relying on every future PR remembering to also write
a 403 test.
"""

from fastapi.routing import APIRoute

from app.auth.deps import get_current_user
from app.deps import require_admin
from app.main import app

# Mutating routes that are deliberately NOT admin-gated, because they're regular-user
# actions authorized some other way (require_username, or a per-league
# require_league_member/admin/owner dependency), not global-admin actions.
NON_ADMIN_MUTATING_ROUTES = {
    ("POST", "/me/username"),
    ("POST", "/leagues"),
    ("PATCH", "/leagues/{league_id}"),
    ("POST", "/leagues/{league_id}/join"),
    ("POST", "/leagues/{league_id}/leave"),
    ("POST", "/leagues/{league_id}/admins/{user_id}"),
    ("DELETE", "/leagues/{league_id}/admins/{user_id}"),
    ("DELETE", "/leagues/{league_id}/members/{user_id}"),
    ("POST", "/leagues/{league_id}/owner"),
    ("POST", "/leagues/{league_id}/invites"),
    ("POST", "/invites/{code}/redeem"),
    ("DELETE", "/invites/{code}"),
}

# Every mutating route on a resource introduced in phases 3/4 must depend on require_admin.
ADMIN_GATED_ROUTES = {
    ("POST", "/events"),
    ("PATCH", "/events/{event_id}"),
    ("DELETE", "/events/{event_id}"),
    ("POST", "/races"),
    ("PATCH", "/races/{race_id}"),
    ("DELETE", "/races/{race_id}"),
    ("POST", "/race-entries"),
    ("PATCH", "/race-entries/{race_entry_id}"),
    ("DELETE", "/race-entries/{race_entry_id}"),
    ("POST", "/teams"),
    ("PATCH", "/teams/{team_id}"),
    ("DELETE", "/teams/{team_id}"),
    ("POST", "/venues"),
    ("PATCH", "/venues/{venue_id}"),
    ("DELETE", "/venues/{venue_id}"),
    ("POST", "/prediction-markets/{prediction_market_id}/settle"),
}


def _api_routes():
    yield from _flatten_routes(app.routes)


def _flatten_routes(wrappers):
    # A route declared directly on an APIRouter (e.g. `@app.get(...)` in main.py, or a leaf
    # route on a sub-router) is an APIRoute directly. A route reached via `include_router`
    # is wrapped in an `_IncludedRouter`, which itself may wrap another `include_router` call
    # (e.g. gameplay's package router composing its five per-resource sub-routers) -- recurse
    # through `original_router.routes` until every leaf APIRoute is found, regardless of
    # nesting depth.
    for wrapper in wrappers:
        if isinstance(wrapper, APIRoute):
            yield wrapper
            continue
        router = getattr(wrapper, "original_router", None)
        if router is None:
            continue
        yield from _flatten_routes(router.routes)


def test_admin_gated_routes_depend_on_require_admin():
    seen = set()
    for route in _api_routes():
        top_level_deps = {sub.call for sub in route.dependant.dependencies}
        for method in route.methods - {"HEAD"}:
            key = (method, route.path)
            if method == "GET" or key in NON_ADMIN_MUTATING_ROUTES:
                continue
            seen.add(key)
            assert require_admin in top_level_deps, (
                f"{method} {route.path} is a mutating route that does not depend on "
                "require_admin -- add the dependency, or add it to "
                "NON_ADMIN_MUTATING_ROUTES if it's deliberately not an admin-only action"
            )

    missing = ADMIN_GATED_ROUTES - seen
    assert not missing, f"expected admin-gated routes not found in the app: {missing}"


def test_non_admin_routes_still_require_authentication():
    """Sanity check the negative case too: every mutating route depends on *some* auth
    (require_admin, which itself wraps get_current_user) -- this would fail loudly if a
    route were accidentally left with no auth dependency at all."""
    for route in _api_routes():
        top_level_deps = {sub.call for sub in route.dependant.dependencies}
        for method in route.methods - {"HEAD"}:
            key = (method, route.path)
            if method == "GET" or key in NON_ADMIN_MUTATING_ROUTES:
                continue
            assert top_level_deps & {require_admin, get_current_user}, (
                f"{method} {route.path} has no auth dependency at all"
            )
