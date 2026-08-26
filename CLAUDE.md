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

**Documentation can be wrong or stale.** This file and the other `CLAUDE.md`/`docs/` files are a
snapshot of decisions made at some point in the past, not ground truth. If something documented
here doesn't match what you observe in the code, contradicts itself, or just doesn't make sense for
the task at hand, do not silently follow it and do not silently override it either — flag the
discrepancy to the user and let them decide how to resolve it.

## Where things live

- `backend/CLAUDE.md` — FastAPI-specific commands, structure, and conventions.
- `web/CLAUDE.md` — Next.js-specific commands, structure, and conventions.
- `mobile/CLAUDE.md` — Flutter-specific commands, structure, and conventions.
- `docs/architecture.md` — the *why* behind cross-cutting technical decisions (e.g. auth, API
  contract). This file covers the *what*/*how* — operational rules Claude needs on every task.
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
- **Closing out tracked work must also update the docs that pointed at it.** If any `CLAUDE.md`
  points at an open issue (e.g. "tracked in issue #2") or a `blocked` label, the PR that closes that
  issue must also update or remove that pointer/label in the same PR — don't leave documentation
  referring to an issue that's already closed.
- **The `superpowers` skill's scratch output (`docs/superpowers/specs/`, `docs/superpowers/plans/`)
  is never committed** — it's git-ignored. If a design decision from that output needs to persist,
  write it into this file, a subfolder `CLAUDE.md`, or `docs/architecture.md` instead.

## Pre-push checks

[lefthook](https://github.com/evilmartians/lefthook) runs two git hooks, scoped to whichever of
`backend/`/`web/` actually changed (config lives in `lefthook.yml` at the repo root; mobile isn't
covered yet — no `mobile/` directory exists):

- **`pre-commit`**: fast, staged-files-only formatting/lint (`ruff format` + `ruff check --fix`
  for `backend/`, `eslint --fix` + `prettier --write` for `web/`).
- **`pre-push`**: lint/typecheck + tests for the changed package(s), per each package's own tools
  (`ruff check` + `pytest` for `backend/`; `eslint` + `tsc --noEmit` + tests for `web/` — `backend/`
  has no separate typechecker, `ruff` is lint+format only). The backend check runs `pytest` against
  a real Postgres reachable at `localhost:5432`, so `docker compose up -d postgres` (or
  `docker compose up -d backend`) must be running locally for it to pass.

`npm install` at the repo root (once, after cloning) installs the `lefthook` binary and wires it
into `.git/hooks` automatically via the `prepare` script — no separate `lefthook install` step.

CI (`.github/workflows/ci.yml`, added by [issue #3](https://github.com/DorneichI/agora/issues/3))
is now in place and is the authoritative check regardless. These hooks remain a fast local
pre-flight before that — don't skip them with `--no-verify`.

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

## Linting / formatting

- Backend: `ruff` (lint + format) + `import-linter` (module-boundary contracts, e.g. `app.leagues`
  must not import `app.gameplay` — see `backend/CLAUDE.md`'s "Domain modules" section).
- Web: ESLint (`eslint-config-next`) + Prettier.
- Mobile: `dart format` + `flutter analyze` (with `flutter_lints`) — Flutter's built-in tools.

## CI

GitHub Actions run lint/typecheck/test for whichever part(s) changed, triggered on every pull
request (this repo is public, so Actions minutes are unlimited/free — no reason to make this
manual). Actual signed mobile release builds (TestFlight/Play) are a separate, manual/tag-triggered
workflow, not part of this check. See `.github/workflows/ci.yml` for the actual workflow (added by
[issue #3](https://github.com/DorneichI/agora/issues/3), now closed).

### Coverage ratchet

CI fails a pull request if `backend/` or `web/` aggregate test coverage drops relative to
`main`, rather than enforcing a fixed percentage (tracked in
[issue #25](https://github.com/DorneichI/agora/issues/25)). This is self-hosted, not
an external service like Codecov — deliberately, since this repo's public status isn't guaranteed
permanent and Codecov's free tier only covers public repos.

- Each package computes a single coverage percentage per CI run (`pytest-cov`'s
  `--cov-report=json` for `backend/`, `vitest`'s `json-summary` coverage reporter for `web/`).
- On every push to `main`, that percentage is saved to a GitHub Actions cache entry
  (`<pkg>-coverage-baseline-<sha>`). On every pull request, the most recent entry for that prefix
  is restored and compared against, via `scripts/check-coverage-ratchet.sh`.
- A 0.5 percentage-point tolerance absorbs rounding noise between runs.
- If no baseline exists yet (first run ever, or the cache entry aged out after 7 days unused),
  the check passes without blocking — it only enforces "don't regress" once it has prior data.
- If the coverage tool's JSON output ever doesn't contain a numeric percentage at the expected key
  (e.g. a `pytest-cov`/`vitest` version bump changes the JSON shape), CI fails loudly right there,
  before caching anything — this stops a bad value from silently becoming the new baseline and
  breaking the ratchet for every subsequent PR.
- **Known limitation**: this ratchets *aggregate* coverage %, not true line-by-line diff/patch
  coverage the way Codecov does — it can theoretically be gamed by adding a large well-covered
  file in the same PR as untested new code. Accepted trade-off for avoiding an external service.

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
- If your local `.env` has fallen behind `.env.example` (new variables added upstream), run
  `npm run sync-env` (wraps `scripts/sync-env.sh`) to regenerate it: it keeps every value you've
  already set, adds any new keys from `.env.example` as placeholders, and warns about (then drops)
  any key your `.env` has that `.env.example` no longer declares. It writes a `.env.bak` backup of
  the old file before overwriting.
- `.env.bak` gets the exact same protection as `.env`: git-ignored (via the existing `.env.*`
  pattern in `.gitignore`) and blocked at the tool-permission level in `.claude/settings.json`.
- **Fresh git worktrees** (`git worktree add`, or an agent's `EnterWorktree`) share this repo's
  history but never get git-ignored files — a new worktree has no `.env` at all. `npm run sync-env`
  handles this too: when the target `.env` doesn't exist yet and the current directory is a linked
  worktree, it seeds values from the same-named file at the main checkout's root before falling
  back to `.env.example`'s placeholders for anything the main checkout's file doesn't have either.
  Since `.env` is blocked from every AI-tool code path (Bash included — not just Read/Edit/Write),
  this command still has to be run by a human, not the agent working in that worktree.
- A dedicated secrets manager (e.g. Doppler, Infisical, 1Password CLI) was considered instead of
  this script and explicitly deferred — this project is small/early-stage, prod hosting isn't
  chosen yet, and whichever host is picked will likely provide its own per-environment secret
  store, making a separate secrets manager redundant. Revisit if the team grows or the chosen host
  doesn't cover this well.

## Still undecided (do not assume — ask before implementing)

- Hosting platform(s) for backend/web/mobile.
- Mobile distribution tooling (e.g. Fastlane, Codemagic) for TestFlight/Play releases.
