# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Agora is a fantasy rowing app: a Python/FastAPI backend and a Next.js frontend, in one repo.

The user building this is not deeply familiar with this stack. Do not assume prior knowledge of
FastAPI, Next.js, or typical patterns in either. Before making a tooling, library, or architecture
choice, present the options and tradeoffs and let the user decide — do not silently pick a default.

## Where things live

- `backend/CLAUDE.md` — FastAPI-specific commands, structure, and conventions.
- `frontend/CLAUDE.md` — Next.js-specific commands, structure, and conventions.
- This file only covers rules that apply across both.

If a task touches both backend and frontend, read both subfolder CLAUDE.md files first.

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

> TODO once backend/frontend exist: fill in the actual lint/typecheck/test commands in `lefthook.yml`
> once those tools are chosen in `backend/CLAUDE.md` / `frontend/CLAUDE.md`.

## Secrets

- Real secrets live in `.env` (git-ignored, never committed). `.env.example` is committed and kept
  in sync as new variables are added.
- `.env` is also blocked at the tool-permission level (`.claude/settings.json`) so it can't be read
  or edited by an AI agent even by accident — this is a hard block, not just an instruction.

## API contract between backend and frontend

FastAPI auto-generates an OpenAPI schema. The frontend generates its TypeScript types from that
schema using [openapi-typescript](https://openapi-ts.dev/) — it does not hand-write API response
types. See `backend/CLAUDE.md` for how the schema is exported, and `frontend/CLAUDE.md` for the
codegen command.

## Still undecided (do not assume — ask before implementing)

- How to bring up backend + frontend together for local dev (e.g. docker compose vs. running both
  separately).
- Python package/dependency manager for the backend.
- JS package manager for the frontend.
- Testing frameworks for each side.
