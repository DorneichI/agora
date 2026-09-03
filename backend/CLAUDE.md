# backend/CLAUDE.md

FastAPI-specific guidance for Claude Code. See the root [`CLAUDE.md`](../CLAUDE.md) for
cross-cutting conventions (git, environments, secrets) and [`docs/architecture.md`](../docs/architecture.md)
for the *why* behind auth and the API contract.

## Stack

- FastAPI, run **async throughout** — routes, DB sessions, everything. This was a deliberate
  choice over sync (FastAPI/Starlette's native concurrency model is async); don't introduce sync
  DB calls or sync route handlers as a shortcut.
- SQLModel on top of SQLAlchemy's async engine (`asyncpg` driver).
- Alembic (async template — `alembic init -t async`) for migrations. Alembic's own migration
  scripts run in a sync context internally; that's normal and not a contradiction of the
  async-throughout rule above — only the app's runtime session is async.
- `uv` for dependency management.
- `ruff` for lint + format (one tool, config in `pyproject.toml`).
- `pytest` (+ `pytest-asyncio`, `asyncio_mode = "auto"`) for tests.

## Running locally

Via Docker Compose from the repo root (bind-mounts this directory, `uvicorn --reload` picks up
edits immediately — no rebuild needed for plain code changes):

```bash
docker compose up backend
```

`GET http://localhost:8000/health` should return `{"status": "ok"}`.

**Dependency changes need more than a rebuild.** `docker-compose.yml` mounts a named volume
(`backend_venv`) at `/app/.venv` so the container's Linux-installed dependencies aren't shadowed
by the host's bind-mounted source directory. That volume is only *populated* from the image the
first time it's created — Docker does not refresh an already-populated named volume from a
rebuilt image. So after changing `pyproject.toml`/`uv.lock`, `docker compose build backend` alone
is not enough; the stale volume will still shadow the freshly-installed dependencies. Remove the
volume too so it gets reseeded from the new image (`docker compose down -v` also works but drops
*every* service's volumes, including the Postgres data volume — usually more than you want):

```bash
docker compose build backend
docker compose rm -sf backend
docker volume rm $(docker volume ls -q --filter name=backend_venv)
docker compose up backend
```

## Commands

Run from inside `backend/` (locally with `uv`, or via `docker compose exec backend <cmd>`):

```bash
uv run pytest              # tests
uv run ruff check .        # lint
uv run ruff format --check .  # format check (drop --check to auto-format)
uv run lint-imports         # import boundary contracts (see "Domain modules" below)
uv run alembic upgrade head   # apply migrations
uv run alembic revision --autogenerate -m "..."  # generate a migration from model changes
uv run python -m scripts.new_domain <name>  # scaffold a new app/<name>/ domain package
```

`DATABASE_URL` (see root `.env.example`) is read by both the app and Alembic's `env.py` — the
`alembic.ini` placeholder value is never used for anything real.

**Promoting a user to admin**: there's no admin signup flow — an already-provisioned user (one
who has logged in via Clerk at least once, so their `User` row exists) is promoted by email via a
one-off script:

```bash
uv run python -m scripts.promote_admin <email>
```

Run as `-m scripts.promote_admin`, not `python scripts/promote_admin.py` — the latter puts
`scripts/` itself on `sys.path` instead of `backend/`, so the script's `from app...` imports fail
with `ModuleNotFoundError`. It only flips `role` on an existing row; it never creates a `User`, and
fails clearly (non-zero exit) if the email has no match.

**Local dev gotcha**: `pytest` creates/drops all tables directly via `SQLModel.metadata` (see
`tests/conftest.py`'s `db_session` fixture) against the same local Postgres Alembic tracks —
it doesn't go through Alembic at all. Running the test suite locally leaves the schema empty while
`alembic_version` still says "head" even though the tables are gone, so a subsequent `alembic
downgrade`/`upgrade` against that same database can fail with errors like `index "..." does not
exist` (Alembic trusts `alembic_version`, not the actual schema, so `upgrade head` alone won't
re-create anything). If that happens, either `docker compose down -v` the `postgres` volume to
reset it, or run `alembic stamp base` (resets the version pointer without touching data) followed
by `alembic upgrade head` (re-runs every migration from scratch).

## Conventions

- **Soft delete**: every table uses `SoftDeleteMixin` (see `docs/architecture.md`'s "Soft delete"
  section) — never a plain unique constraint on a soft-deletable table, always a partial unique
  index scoped to `WHERE deleted_at IS NULL`.
- **HTTP status codes**: which situation maps to which code (401 vs 403 vs 404 vs 409 vs 410 vs
  422, and 200 vs 201 vs 204) is a written convention, not a per-endpoint judgment call — see
  `docs/architecture.md`'s "HTTP status codes" section.
- No hand-rolled password storage — auth identity comes from Clerk (see
  `docs/architecture.md#auth`); the backend only verifies Clerk-issued JWTs.
- **Authorization**: `User.role` is a plain `str` (`"user"` | `"admin"`, default `"user"`) — no DB
  enum, no Clerk Organizations/Roles. Gate a route to admins only with `Depends(require_admin)`
  (`app/deps.py`, layered on top of `require_username`, which itself depends on `get_current_user`
  — both in `app/auth/deps.py`) rather than checking `user.role` inline in the route body.
- **Response schemas**: never use a table model directly as a route's `response_model` — pair
  every table with a `*Read` SQLModel (e.g. `UserRead`, `LeagueRead`) that excludes
  `SoftDeleteMixin`'s bookkeeping columns (`created_at`/`updated_at`/`deleted_at`) from the API
  response.
- **Route naming for multi-word resources**: kebab-case, e.g. `RaceEntry` -> `/race-entries`
  (established by issue #44's `race_entries.py` router, the first two-word resource in the API).
- **List filters**: an optional filter on a list endpoint is a plain query param declared
  with a `None` default (`event_id: int | None = None`, placed before the route's
  `Depends(...)` params) — not `Annotated[..., Query(...)]`, which is only worth reaching
  for once a filter needs a description, alias, or bounds in the OpenAPI output. The router
  passes it through to the domain's `repository.py`, which conditionally appends the `WHERE`
  — routers never build queries themselves (see "Domain modules" below). A filter value
  matching nothing yields `200 []`, never a 404: these are filter semantics, not a lookup,
  and "no rows match" is indistinguishable from a parent that legitimately has no children
  yet. Non-integer input yields `422` automatically from the type annotation, so no
  hand-written validation is needed. (First case: issue #92's `/races?event_id=` and
  `/race-entries?race_id=`.)

## Domain modules

Some resources outgrow "one model file + one router file" once other code needs to depend on
them without reaching into scattered internals (issue #63 was the first case: leagues, before
gameplay/chat needed to reference league membership). When that happens, give the resource its
own package instead of adding another shared cross-cutting layer:

- `app/<domain>/models.py` -- the SQLModel table + `*Read` classes for this domain, replacing
  what used to live in `app/models/<name>.py`.
- `app/<domain>/repository.py` -- plain async functions wrapping every
  `session.execute(select(...))` query this domain's routers/deps need, so no other module has
  to write a raw query against this domain's tables. The one deliberate exception:
  `app/crud_helpers.py`'s shared `get_or_404`/`validate_fk_exists`/`assert_not_referenced`
  helpers, which every domain's routers use, query directly and sit outside this per-domain rule --
  they're generic across all domains, not specific to one, which is why they live in shared
  `app/crud_helpers.py` rather than any single domain's `repository.py`.
- `app/<domain>/deps.py` -- any `require_*`/`get_*` FastAPI dependency specific to this domain
  (e.g. `require_league_member`), moved out of the shared `app/deps.py`.
- `app/<domain>/router.py` -- the FastAPI router(s) for this domain, wired into `app/main.py` as
  `from app.<domain>.router import router as <domain>_router`. If this single file grows too
  large for one resource's endpoints to stay readable together (issue #87 was the first case),
  split it into an `app/<domain>/routers/` package instead: one file per resource, a shared
  helper module for anything genuinely cross-resource, and an
  `app/<domain>/routers/__init__.py` that composes the per-resource `APIRouter`s into one
  `router` -- `main.py`'s import becomes
  `from app.<domain>.routers import router as <domain>_router` (package, not module).

`scripts/new_domain.py` (`uv run python -m scripts.new_domain <name>`) generates all four
files' skeletons in one step. It deliberately does not wire `app/main.py` or add an
import-linter contract for the new domain -- both need a judgment call about what the domain
should be allowed to import -- but prints a reminder for each so neither gets forgotten.

`app/deps.py` stays reserved for genuinely generic, cross-domain concerns (currently just
`require_admin` — identity verification itself (`get_current_user`, `require_username`) lives in
`app/auth/deps.py`, behind the `IdentityProvider` port in `app/auth/ports.py`/`clerk_provider.py`).
`app/models/__init__.py`
does not re-export a domain package's symbols -- import them from `app.<domain>.models` directly
(no backwards-compat shim; see root `CLAUDE.md`'s rule against re-exporting types).

This "foundation stays domain-agnostic" rule is enforced, not just documented: an import-linter
`forbidden` contract (`pyproject.toml`) blocks `app.auth`, `app.deps`, `app.routers`, `app.db`,
`app.crud_helpers`, `app.soft_delete`, and `app.models` from importing any domain package. If a
piece of shared infrastructure ever needs something domain-specific, that's a sign the logic
belongs in the domain's own `deps.py`/`repository.py` instead of being added to the shared layer.

`app/leagues/` and `app/gameplay/` are both built this way (issues #63 and #64). `app.leagues`
and `app.gameplay` are mutually independent -- enforced by an import-linter `independence`
contract, not the one-way `forbidden` contract this section used to describe -- so either domain
can be removed without the other noticing. Both use the `routers/` package split described above
-- `app/gameplay/router.py` was the first to need this split (issue #87), and
`app/leagues/router.py` followed once the file-length check flagged it (issue #102) — leagues +
invites endpoints split into `app/leagues/routers/leagues.py` and
`app/leagues/routers/invites.py`.

**Cross-domain composition gets its own dedicated package, never bolted onto either domain it
reads from.** `GET /leagues/{league_id}/standings` needs both league membership (`app.leagues`)
and aggregated prediction points (`app.gameplay`) at once -- but neither domain may import the
other, so this endpoint lives in `app.standings`, a small package whose only job is depending on
both. `app.standings` is deliberately exempt from the `app.leagues`/`app.gameplay` independence
contract above (it's the one place allowed to import either) and from the foundation-independence
contract above (it's not foundation -- depending on domains is its entire purpose); its own
`forbidden_modules` list adds `app.standings` so foundation can't import it either. Any future
endpoint spanning two-or-more domains gets the same treatment: a new small `app.<name>` package,
not a home inside one of the domains it reads from. Give such a module a header comment
explaining why it's separate -- that reasoning is invisible from the route path alone (issue #99
was the first case, when this still lived inside `app.gameplay`).
