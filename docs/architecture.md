# Architecture decisions

This file records *why* cross-cutting technical decisions were made, not just what they are.
For the operational rules Claude Code needs on every task, see the root [`CLAUDE.md`](../CLAUDE.md).

## Auth

Managed identity provider: [Clerk](https://clerk.com/), used across all three pieces, with
passkeys (Touch ID/Face ID/Windows Hello via WebAuthn) as a goal everywhere:

**Passkeys are currently blocked**: Clerk gates passkey/biometric sign-in behind a paid plan,
discovered while implementing issue #16. The web login UI (#16) shipped with email/password and
Google OAuth only; whether to pursue passkeys (and a paid Clerk plan) is still an open decision,
not yet tracked in a follow-up issue. Don't assume passkeys work anywhere in the stack until
that's resolved.

- **Backend**: verifies the JWT Clerk issues — no hand-rolled password storage/reset flows.
- **Web**: Clerk's official Next.js SDK directly. Passkeys are mature and documented here
  (once the paid-plan blocker above is resolved).
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

## API contract between backend and clients

FastAPI auto-generates an OpenAPI schema. Both clients generate code from that schema rather than
hand-writing request/response types — the schema is the single source of truth:

- `web/` uses [openapi-typescript](https://openapi-ts.dev/) — types only, hand-written fetch calls.
- `mobile/` uses `openapi_generator` configured for **models only** (not its generated client) —
  same principle as web: generated types, hand-written calls (via `dio`/`http`).

See `backend/CLAUDE.md` for how the schema is exported, and `web/CLAUDE.md` / `mobile/CLAUDE.md`
for each side's codegen command.

## Soft delete

Every table uses `SoftDeleteMixin` (`backend/app/soft_delete.py`) instead of participating in real
`DELETE`s. A row's `deleted_at` stays `NULL` while it's active and gets set to a timestamp instead
of the row being removed.

- **`SoftDeleteMixin`**: an SQLModel mixin providing `id`, `created_at`, `updated_at`, and a
  nullable `deleted_at`. Any table model gets soft-delete for free by inheriting it:
  `class Foo(SoftDeleteMixin, SQLModel, table=True)`.
- **Read filtering**: a `do_orm_execute` SQLAlchemy event, registered globally on `Session`, adds a
  `deleted_at IS NULL` criterion (via `with_loader_criteria`) to every SELECT against a
  `SoftDeleteMixin` model — including joins and eager/lazy loads. Pass
  `.execution_options(include_deleted=True)` on a specific query to see soft-deleted rows too (e.g.
  an admin "restore" screen).
- **Write rewriting**: a `before_flush` event, also registered globally on `Session`, intercepts
  any `session.delete(obj)` call on a `SoftDeleteMixin` instance and rewrites it into
  `obj.deleted_at = now()` before the flush proceeds, so no real `DELETE` is ever issued for these
  tables.
- **Partial unique indexes only**: any unique constraint on a soft-deletable table must be scoped
  to `WHERE deleted_at IS NULL`, never a plain unique constraint — otherwise a soft-deleted row
  permanently blocks reuse of that value (e.g. re-registering a deleted user's email, rejoining a
  league after leaving). Declare it in `__table_args__`:

  ```python
  from sqlalchemy import Index, text

  class User(SoftDeleteMixin, SQLModel, table=True):
      email: str
      __table_args__ = (
          Index(
              "ix_user_email_active",
              "email",
              unique=True,
              postgresql_where=text("deleted_at IS NULL"),
          ),
      )
  ```

  Alembic's `--autogenerate` does not reliably detect `postgresql_where` — always check generated
  migrations by hand for indexes on soft-deletable tables.
