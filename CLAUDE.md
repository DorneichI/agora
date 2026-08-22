# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Agora is a fantasy rowing app with three deployable pieces in one repo:

- `backend/` — Python/FastAPI API.
- `web/` — Next.js web frontend.
- `mobile/` — Flutter app (Android + iOS).

The user building this is not deeply familiar with this stack. Do not assume prior knowledge of
FastAPI, Next.js, Flutter, or typical patterns in any of them. Before making a tooling, library, or
architecture choice, present the options and tradeoffs and let the user decide — do not silently
pick a default.

## Where things live

- `backend/CLAUDE.md` — FastAPI-specific commands, structure, and conventions.
- `web/CLAUDE.md` — Next.js-specific commands, structure, and conventions.
- `mobile/CLAUDE.md` — Flutter-specific commands, structure, and conventions.
- This file only covers rules that apply across two or more of them.

If a task touches more than one of backend/web/mobile, read each relevant subfolder's CLAUDE.md
first.

## Durable knowledge belongs in this repo, not in AI-tool memory

Do not rely on any AI coding assistant's built-in memory/notes feature to retain project
knowledge. Every convention, decision, and piece of context that should persist must be written
into this repo's documentation (this file, the subfolder `CLAUDE.md` files, or `docs/`). The goal
is that the project is fully understandable by switching to a different coding agent with zero
loss of "tribal knowledge."

## Git conventions

- **Commit messages** follow [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): description` (e.g. `feat(backend): add race scoring endpoint`).
- **Branch names** follow the same `type` prefixes as commits: `type/short-description` (e.g. `feat/add-boat-lineup`, `fix/race-scoring-bug`).
- **PRs are always squash-merged** into `main`, so history stays linear (one commit per PR on top).
  This is enforced at the repo level — merge commits and rebase merges are disabled in GitHub
  settings, only squash merge is available.

## Pre-push checks

A [lefthook](https://github.com/evilmartians/lefthook) `pre-push` hook runs lint, typecheck, and
tests for whichever part(s) of the repo changed, before a push is allowed to proceed. Config lives
in `lefthook.yml` at the repo root.

> TODO once backend/web/mobile exist: fill in the actual lint/typecheck/test commands in
> `lefthook.yml`.

## Local dev environment

- `backend/` and `web/` run via Docker Compose (`docker-compose.yml` at the repo root). Both
  services bind-mount their source directory into the running container and run their dev server
  in watch/reload mode (`uvicorn --reload` for the backend, `next dev` for web) — editing code on
  the host takes effect immediately, no image rebuild needed. The image only needs rebuilding when
  a dependency (uv lockfile / package.json) changes.
- `mobile/` runs natively via `flutter run` (Docker isn't practical for iOS/Android builds) and
  points at the backend's dev URL through Flutter build flavors (see `mobile/CLAUDE.md`).
- Python dependency management: [uv](https://github.com/astral-sh/uv).
- Web (`web/`) package manager: npm.
- Backend tests: pytest. Web tests: Vitest (unit/component) + Playwright (e2e). Mobile tests:
  `flutter test` (unit/widget) + `integration_test` (e2e).

## Backend data layer

- Database: Postgres.
- ORM: [SQLModel](https://sqlmodel.tiangolo.com/) (built on SQLAlchemy, same author as FastAPI —
  one class defines both the DB table and the API schema).
- Migrations: Alembic.

## Auth

Managed identity provider: [Clerk](https://clerk.com/) — implements OAuth2/OIDC + JWT under the
hood, has first-class Next.js and Flutter SDKs, and the FastAPI backend only needs to verify the
JWT it issues (no hand-rolled password storage, reset flows, or token rotation to own).

## Linting / formatting

- Backend: `ruff` (lint + format, one tool).
- Web: ESLint (`eslint-config-next`) + Prettier.
- Mobile: `dart format` + `flutter analyze` (with `flutter_lints`) — Flutter's built-in tools.

## CI

GitHub Actions run lint/typecheck/test for whichever part(s) changed, triggered on every pull
request (this repo is public, so Actions minutes are unlimited/free — no reason to make this
manual). Actual signed mobile release builds (TestFlight/Play) are a separate, manual/tag-triggered
workflow, not part of this check.

> TODO once backend/web/mobile exist: write `.github/workflows/ci.yml` using `astral-sh/setup-uv`,
> `actions/setup-node`, and `subosito/flutter-action`, path-filtered per stack.

## Environments

- Two tiers beyond local dev: **staging** and **prod**. No preprod for now — can be added later
  without changing this shape.
- Backend/web: `main` auto-deploys to staging; prod is a promotion of that same build (not a
  rebuild from source), triggered manually or by tag.
- Mobile has no hosted "staging" — instead it's build **flavors** (dev/staging/prod) selecting the
  backend URL, distributed via app-store tracks: TestFlight / Play internal-or-closed testing
  stands in for staging, App Store / Play production track is prod.
- Hosting platform(s) for each piece, and mobile release tooling (e.g. Fastlane, Codemagic), are
  still open — see below.

## Secrets

- Real secrets live in `.env` (git-ignored, never committed). `.env.example` is committed and kept
  in sync as new variables are added.
- `.env` is also blocked at the tool-permission level (`.claude/settings.json`) so it can't be read
  or edited by an AI agent even by accident — this is a hard block, not just an instruction.

## API contract between backend and clients

FastAPI auto-generates an OpenAPI schema. Both clients generate code from that schema rather than
hand-writing request/response types — the schema is the single source of truth:

- `web/` uses [openapi-typescript](https://openapi-ts.dev/) — types only, hand-written fetch calls.
- `mobile/` uses `openapi_generator` configured for **models only** (not its generated client) —
  same principle as web: generated types, hand-written calls (via `dio`/`http`).

See `backend/CLAUDE.md` for how the schema is exported, and `web/CLAUDE.md` / `mobile/CLAUDE.md`
for each side's codegen command.

## Still undecided (do not assume — ask before implementing)

- Hosting platform(s) for backend/web/mobile.
- Mobile distribution tooling (e.g. Fastlane, Codemagic) for TestFlight/Play releases.
