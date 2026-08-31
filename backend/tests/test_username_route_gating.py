"""Regression guard for issue #52's onboarding gate: every route must depend on
require_username or require_admin (which itself depends on require_username), except the
explicit exemptions below -- a user who hasn't set a username yet must be blocked
everywhere else. Nothing else in the test suite would catch a future route that forgets
this dependency; each router's own tests only exercise the routes it defines, so a new
route added without the gate would just silently accept an un-onboarded caller. This walks
the actual FastAPI route table instead of relying on every future PR remembering to also
write a 403 test.
"""

from fastapi.routing import APIRoute

from app.auth.deps import require_username
from app.deps import require_admin
from app.main import app

# Routes that must be reachable by a user who hasn't set a username yet (or, for /health, by
# anyone at all) are explicitly exempt from the require_username/require_admin gate.
EXEMPT_ROUTES = {
    ("GET", "/health"),
    ("GET", "/me"),
    ("POST", "/me/username"),
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


def test_every_route_depends_on_username_gate_except_exemptions():
    seen = set()
    for route in _api_routes():
        top_level_deps = {sub.call for sub in route.dependant.dependencies}
        for method in route.methods - {"HEAD"}:
            key = (method, route.path)
            seen.add(key)
            if key in EXEMPT_ROUTES:
                continue
            assert top_level_deps & {require_username, require_admin}, (
                f"{method} {route.path} does not depend on require_username or require_admin"
            )

    missing = EXEMPT_ROUTES - seen
    assert not missing, f"expected exempt routes not found in the app: {missing}"
