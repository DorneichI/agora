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
edits immediately — no rebuild needed unless `pyproject.toml`/`uv.lock` changes):

```bash
docker compose up backend
```

`GET http://localhost:8000/health` should return `{"status": "ok"}`.

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

## Conventions

- **Soft delete**: every table uses `SoftDeleteMixin` (see `docs/architecture.md`'s "Soft delete"
  section) — never a plain unique constraint on a soft-deletable table, always a partial unique
  index scoped to `WHERE deleted_at IS NULL`.
- No hand-rolled password storage — auth identity comes from Clerk (see
  `docs/architecture.md#auth`); the backend only verifies Clerk-issued JWTs.
