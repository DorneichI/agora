# Roadmap

This file lays out the path from an empty repo to a first working product, in the order the work
will happen. It's the *narrative* — for the *why* behind cross-cutting technical decisions it
references, see [`docs/architecture.md`](architecture.md); for day-to-day operational rules, see
the root [`CLAUDE.md`](../CLAUDE.md). Concrete, ready-to-pick-up work for each phase is filed as
GitHub Issues, linked here once they exist.

## Sequencing

`mobile/` is deferred. Work starts on `backend/` and `web/` only — `mobile/` picks up once those
are on solid footing.

## Phase 1 — Backend core

Users can:

- create an account
- create a league
- add themselves to a league

League invites are deferred — not scheduled into a phase yet (see issue #8).

## Phase 2 — Auth (web)

Users can log in on web via:

- Google OAuth
- email + password
- passkeys (Touch ID / Face ID / Windows Hello via WebAuthn)

These map to the identity-provider decision already recorded in
[`architecture.md#auth`](architecture.md#auth) (Clerk).

**Open question, not yet decided:** whether to add two-factor via an authenticator app (TOTP) on
top of the above. To be discussed separately before it's built.

### i. Sidequest — fully end-to-end encrypted league group chats

Exploratory only — not committed scope for this phase. Before any implementation: is this
feasible/worth building, and what would it take (encryption protocol choice, key management,
how it fits the backend's data model)?
