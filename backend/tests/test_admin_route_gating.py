"""Regression guard for backend/CLAUDE.md's authorization convention: "Gate a route to
admins only with Depends(require_admin) ... rather than checking user.role inline in the
route body."

Nothing else in the test suite would catch a future mutating route that forgets
`Depends(require_admin)` -- each router's own tests only exercise the routes it defines, so
a route added without the dependency would just silently accept non-admin callers. This
walks the actual FastAPI route table instead of relying on every future PR remembering to
also write a 403 test.
"""

from fastapi.routing import APIRoute

from app.deps import get_current_user, require_admin
from app.main import app

# Every mutating route on a resource introduced in phases 3/4 must depend on require_admin.
# Pre-existing routes (leagues, me) are intentionally excluded: league creation/join/leave are
# regular-user actions, not admin actions, so they depend on get_current_user instead.
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
}


def _api_routes():
    for wrapper in app.routes:
        router = getattr(wrapper, "original_router", None)
        if router is None:
            continue
        yield from (route for route in router.routes if isinstance(route, APIRoute))


def test_admin_gated_routes_depend_on_require_admin():
    seen = set()
    for route in _api_routes():
        top_level_deps = {sub.call for sub in route.dependant.dependencies}
        for method in route.methods - {"HEAD"}:
            key = (method, route.path)
            if key not in ADMIN_GATED_ROUTES:
                continue
            seen.add(key)
            assert require_admin in top_level_deps, (
                f"{method} {route.path} does not depend on require_admin"
            )

    missing = ADMIN_GATED_ROUTES - seen
    assert not missing, f"expected admin-gated routes not found in the app: {missing}"


def test_non_admin_routes_still_require_authentication():
    """Sanity check the negative case too: every mutating route on the resources above
    depends on *some* auth (require_admin, which itself wraps get_current_user) -- this
    would fail loudly if a route were accidentally left with no auth dependency at all."""
    for route in _api_routes():
        top_level_deps = {sub.call for sub in route.dependant.dependencies}
        for method in route.methods - {"HEAD"}:
            key = (method, route.path)
            if key not in ADMIN_GATED_ROUTES:
                continue
            assert top_level_deps & {require_admin, get_current_user}, (
                f"{method} {route.path} has no auth dependency at all"
            )
