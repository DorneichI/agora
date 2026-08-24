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

## Phase 3 — Admin authorization

Foundation only — no new user-facing capability by itself; Phase 4 is its first consumer.

- A `role` column on `User` (`"user"` | `"admin"`, default `"user"`), checked by a
  `require_admin` dependency that rejects non-admins.
- Admins authenticate exactly like any other user, via Clerk — there is no parallel login
  system. Authorization (can this user manage race data) lives entirely in this app's own
  database, not in Clerk's Organizations/Roles features.
- Bootstrapping the first admin: a one-off seed script promotes an already-provisioned user
  (identified by email) to `"admin"`. The target user must have already logged in at least once
  via Clerk — so their `User` row exists — before the script can run.

## Phase 4 — Races & Results

Admins can record real-world race data — events, venues, teams, races, and results — that later
phases (predictions, scoring) will build on. Everything here is historical fact; it deliberately
does not yet include user predictions or points.

- Entities: `Team` (name, school, mascot, image), `Venue` (name, location, image), `Event` (name,
  description, venue, format, date range, image), `Race` (event, boat class, level, round),
  `RaceEntry` (race, team, level, time, status: finished/dnf/dns/dq).
- `Race.level` is the race's nominal/official category (e.g. "3rd Varsity"); `RaceEntry.level` is
  what a specific team actually sent, since a team without enough depth may enter a lower boat
  into a higher-numbered race than its official level.
- Images are a plain `image_url` field (an admin pastes a link) — no upload/object storage
  infrastructure, since the hosting platform is still undecided (see root `CLAUDE.md`'s "Still
  undecided" section).
- Every entity tracks `created_by`/`updated_by` (last editor only, not a full change history) — a
  fuller audit log is deferred until real disputes over results actually come up, since there's no
  live scoring yet for that to matter.
- Standard CRUD routes per entity (`POST`/`GET`/`PATCH`/`DELETE`); mutations require admin (Phase
  3), reads require any authenticated user.
- **Deliberately out of scope**: user predictions and the points/scoring system. The scoring
  formula (duel margin vs. multi-boat vs. tournament outcomes) isn't settled yet, and the
  prediction schema depends on it — both come in a later phase once decided.
