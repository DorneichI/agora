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

League invites are scheduled as Phase 7 (see issue #55).

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
- **Deliberately out of scope**: user predictions and the points/scoring system — see Phase 8.

## Phase 5 — Usernames

Users must pick a unique username on first login before doing anything else.

- `User.display_name` is replaced by `User.username`: lowercase, `^[a-z0-9_]{3,20}$`, unique,
  permanent once set. A new `require_username` dependency blocks every authenticated route except
  the one that sets it, so a user can't do anything else until they've chosen one. `/me`
  provisioning no longer seeds a name from Clerk's claims.

## Phase 6 — League roles

Leagues gain an owner (defaults to creator) and per-league admins, sitting above the plain-member
role introduced in Phase 2.

- `League` gains a mutable `owner_id` (distinct from the existing immutable `created_by`).
- `LeagueUser` gains a `role` (`"member"` | `"admin"`); the owner's row is always `"admin"` too.
- Any admin can promote a member to admin or kick a non-admin member. Only the owner can demote
  an admin, kick an admin, or transfer ownership (to any member, who becomes admin if not
  already). The owner can't leave the league without transferring ownership first.

## Phase 7 — League invites

League invites (issues #54, #55). Joining a league becomes gated by visibility and invite settings
instead of the open `POST /leagues/{id}/join` from Phase 2.

- `League` gains `visibility` (`"public"` | `"private"`, default `"private"`), `invite_policy`
  (`"anyone"` | `"admins_only"` | `"owner_only"`, default `"owner_only"`, meaningful only when
  private), and `settings_policy` (`"owner_only"` | `"admins_only"`, default `"owner_only"`)
  governing who can change `visibility`/`invite_policy` — `settings_policy` itself can only ever
  be changed by the owner.
- New `LeagueInvite` table (`code`, `league_id`, `created_by`, `target_user_id` nullable,
  `expires_at`, `redeemed_at`, `revoked_at`). Public leagues get open, unlimited-use links
  (7-day expiry); private leagues get single-use codes targeted at one username (7-day expiry,
  requires Phase 5). Either can be revoked early by its creator, an admin, or the owner. The
  existing plain `POST /leagues/{id}/join` now only works on public leagues — private leagues
  require a redeemed invite.

## Phase 8 — Predictions & Scoring

Users can predict race outcomes before results are known, and earn points once real results are
recorded (Phase 4). Scoring is built as a composable framework of independent components rather
than a fixed formula, so new prediction types can be added later without rewriting what's already
shipped. Tracked as [milestone #8](https://github.com/DorneichI/agora/milestone/8).

- Prework (issues [#92](https://github.com/DorneichI/agora/issues/92),
  [#93](https://github.com/DorneichI/agora/issues/93)): `event_id`/`race_id` query filters on the
  existing `races`/`race-entries` list endpoints, and a required freeform `name` field on `Race` —
  both needed before markets can reference races usefully.
- `PredictionMarket` (one per race, holds a `scoring_config`) and `Prediction` (one per user per
  market: a picked team, and optionally a margin threshold) — both live inside `app.gameplay`, not
  a separate module (issue [#94](https://github.com/DorneichI/agora/issues/94)).
- Scoring is composed from independent **components**, each self-declaring which races it's
  eligible for and how it turns a result into points (issue
  [#95](https://github.com/DorneichI/agora/issues/95)):
  - **Winner** — pick the race's winner. Eligible for any race with 2+ entries. Pays either a flat
    amount per correct pick, or a pari-mutuel pool split equally among everyone who picked
    correctly.
  - **Margin** — pick a margin threshold (runner-up's time minus the winner's time, regardless of
    field size); only pays if the winner pick was also correct. Flat mode pays
    `base × 2^(threshold / M)` (bolder threshold = bigger payout if it hits); pool mode splits a
    fixed pool equally among everyone whose threshold was covered, ignoring boldness. `M` (the
    "typical margin" reference constant) is either a single global value or set per-market.
  - Both components void gracefully when results don't support grading them (no finisher at all
    voids the whole market; fewer than two finishers voids just the margin component).
- Market creation, prediction submission, and settlement endpoints (issues
  [#96](https://github.com/DorneichI/agora/issues/96),
  [#97](https://github.com/DorneichI/agora/issues/97),
  [#98](https://github.com/DorneichI/agora/issues/98)).
- League standings aggregating prediction points (issue
  [#99](https://github.com/DorneichI/agora/issues/99)) — lives in `app.gameplay`, not
  `app.leagues`, since predictions are global per-user and the import-linter contract forbids
  `leagues → gameplay`.
- **Deliberately out of scope for this phase**: weekly stake/bankroll allocation across multiple
  bets (a real design problem — naive stake-weighting lets a player risklessly max-bet on obvious
  wins; a real fix likely needs market-pricing dynamics, deferred to its own future design
  conversation), multi-boat-specific components beyond what already generalizes (exact finish
  order, etc.) and tournament/bracket scoring (separate future phases), real continuous-pricing
  prediction markets (Kalshi/Polymarket-style order books — explicitly rejected as too much new
  infrastructure for this phase), and exact market lock timing (deferred, needs its own
  conversation about when predictions close relative to race start).
