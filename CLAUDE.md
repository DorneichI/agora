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

**A recommendation is not a decision.** Giving a recommendation (even when asked "what do you
think?") does not make it settled, and a vague or non-committal reply is not confirmation. A choice
only becomes final once the user makes an explicit, unambiguous selection (e.g. answering a direct
question with a specific option). Only write something into this repo's documentation as decided
after that has happened — not before.

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
- **Branch names** follow the same `type` prefixes as commits, plus the GitHub issue number they
  close: `type/issue-number-short-description` (e.g. `feat/12-add-boat-lineup`,
  `fix/47-race-scoring-bug`).
- **PRs are always squash-merged** into `main`, so history stays linear (one commit per PR on top).
  This is enforced at the repo level — merge commits and rebase merges are disabled in GitHub
  settings, only squash merge is available.
- **`main` is protected**: direct pushes are rejected (including for admins) — every change goes
  through a PR.
- **Task tracking is plain GitHub Issues** — no separate TODO file, no Projects board (for now).
  Pull work from Issues; reference the issue being closed in the PR body (`Closes #12`) so merging
  auto-closes it. The branch name's issue number (above) makes this traceable even before the PR
  exists.

## Pre-push checks

A [lefthook](https://github.com/evilmartians/lefthook) `pre-push` hook runs lint, typecheck, and
tests for whichever part(s) of the repo changed, before a push is allowed to proceed. Config lives
in `lefthook.yml` at the repo root. Filling in the actual commands is tracked in
[issue #2](https://github.com/DorneichI/agora/issues/2).

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

Managed identity provider: [Clerk](https://clerk.com/), used across all three pieces, with
passkeys (Touch ID/Face ID/Windows Hello via WebAuthn) as a goal everywhere:

- **Backend**: verifies the JWT Clerk issues — no hand-rolled password storage/reset flows.
- **Web**: Clerk's official Next.js SDK directly. Passkeys are mature and documented here.
- **Mobile**: does **not** use `clerk_flutter` (Clerk's Flutter SDK is beta and
  community-maintained, not officially supported by Clerk, and has no documented passkey support).
  Instead, the app opens Clerk's hosted sign-in page in a **system-browser sheet**
  (`ASWebAuthenticationSession` on iOS, Chrome Custom Tabs on Android — via a package like
  `flutter_web_auth_2`), then receives the session back through a deep link. This works because a
  system-browser sheet is a real browser context with full WebAuthn support (unlike an embedded
  WebView, which doesn't support passkeys reliably) — so mobile gets the same passkey support as
  web without depending on Clerk's unsupported native mobile SDK. Exact redirect-URI/deep-link
  wiring (and possibly an iOS Associated Domains entitlement) is an implementation detail to work
  out and test when this is actually built.

## Linting / formatting

- Backend: `ruff` (lint + format, one tool).
- Web: ESLint (`eslint-config-next`) + Prettier.
- Mobile: `dart format` + `flutter analyze` (with `flutter_lints`) — Flutter's built-in tools.

## CI

GitHub Actions run lint/typecheck/test for whichever part(s) changed, triggered on every pull
request (this repo is public, so Actions minutes are unlimited/free — no reason to make this
manual). Actual signed mobile release builds (TestFlight/Play) are a separate, manual/tag-triggered
workflow, not part of this check. Writing the actual workflow is tracked in
[issue #3](https://github.com/DorneichI/agora/issues/3).

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
