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
uv run alembic upgrade head   # apply migrations
uv run alembic revision --autogenerate -m "..."  # generate a migration from model changes
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
- No hand-rolled password storage — auth identity comes from Clerk (see
  `docs/architecture.md#auth`); the backend only verifies Clerk-issued JWTs.
- **Authorization**: `User.role` is a plain `str` (`"user"` | `"admin"`, default `"user"`) — no DB
  enum, no Clerk Organizations/Roles. Gate a route to admins only with `Depends(require_admin)`
  (`app/deps.py`, layered on top of `require_username`, which itself depends on `get_current_user`)
  rather than checking `user.role` inline in the route body.
- **Response schemas**: never use a table model directly as a route's `response_model` — pair
  every table with a `*Read` SQLModel (e.g. `UserRead`, `LeagueRead`) that excludes
  `SoftDeleteMixin`'s bookkeeping columns (`created_at`/`updated_at`/`deleted_at`) from the API
  response.
- **Route naming for multi-word resources**: kebab-case, e.g. `RaceEntry` -> `/race-entries`
  (established by issue #44's `race_entries.py` router, the first two-word resource in the API).
