# Roadmap

This file lays out the path from an empty repo to a first working product, in the order the work
will happen. It's the *narrative* — for the *why* behind cross-cutting technical decisions it
references, see [`docs/architecture.md`](architecture.md); for day-to-day operational rules, see
the root [`CLAUDE.md`](../CLAUDE.md). Concrete, ready-to-pick-up work for each phase is filed as
GitHub Issues, linked here once they exist.

## Sequencing

`mobile/` is deferred. Work starts on `backend/` and `web/` only — `mobile/` picks up once those
are on solid footing.

Auth comes before backend-core features (leagues): building leagues against a throwaway
self-registration flow would mean rework once real auth lands. Doing auth first means real `User`
rows get provisioned from a verified Clerk login from day one — no backfill later.

## Phase 1 — Auth (web)

Users can log in on web via:

- Google OAuth
- email + password
- passkeys (Touch ID / Face ID / Windows Hello via WebAuthn)

These map to the identity-provider decision already recorded in
[`architecture.md#auth`](architecture.md#auth) (Clerk). There is no separate self-registration
endpoint — a local `User` row is provisioned automatically the first time someone completes a
Clerk login, keyed by Clerk's `clerk_id`.

**Open question, not yet decided:** whether to add two-factor via an authenticator app (TOTP) on
top of the above. To be discussed separately before it's built.

### i. Sidequest — fully end-to-end encrypted league group chats

Exploratory only — not committed scope for this phase. Before any implementation: is this
feasible/worth building, and what would it take (encryption protocol choice, key management,
how it fits the backend's data model)?

## Phase 2 — Backend core (leagues)

Users can:

- create a league
- add themselves to a league

League invites are deferred — not scheduled into a phase yet (see issue #8).
